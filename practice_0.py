import pandas as pd
import camelot
import unicodedata
import re
import io
import calendar
import pdfplumber
import datetime
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account

# --- ユーティリティ関数 ---

def extract_year_month_from_text(text):
    """PDF内のテキストから年月を抽出する"""
    if not text: return None, None
    text = unicodedata.normalize('NFKC', text)
    # 202X年 or 202X/X/X の形式を探す
    year_match = re.search(r'(202\d)', text)
    month_match = re.search(r'(\d{1,2})月', text)
    
    y = int(year_match.group(1)) if year_match else datetime.datetime.now().year
    m = int(month_match.group(1)) if month_match else None
    
    # 3月度などの表記がない場合、日付スタンプから推測
    if m is None:
        date_stamp = re.search(r'202\d[/\- ](\d{1,2})[/\- ]', text)
        if date_stamp: m = int(date_stamp.group(1))
            
    return y, m

def normalize_text(text):
    """テキストから空白・改行を除去し比較しやすくする"""
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　\n]', '', unicodedata.normalize('NFKC', text)).lower()

# --- メインロジック ---

def get_gdrive_service(secrets):
    creds = service_account.Credentials.from_service_account_info(
        secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build('drive', 'v3', credentials=creds)

def pdf_reader(pdf_stream, target_staff):
    """
    複数ページのPDFから対象者のシフトを抽出。
    T1/T2両方のレイアウトに対応。
    """
    clean_target = normalize_text(target_staff)
    pdf_stream.seek(0)
    
    # 一時ファイルとして保存（Camelot用）
    with open("temp.pdf", "wb") as f: f.write(pdf_stream.getbuffer())
    
    # 年月の特定
    with pdfplumber.open("temp.pdf") as pdf:
        full_text = "\n".join([p.extract_text() or "" for p in pdf.pages])
        year, month = extract_year_month_from_text(full_text)

    # テーブル抽出 (複数ページ対応)
    try:
        tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
        if len(tables) == 0:
            tables = camelot.read_pdf("temp.pdf", pages='all', flavor='stream')
    except: return {}, year, month
    
    table_dictionary = {}
    for table in tables:
        df = table.df
        if df.empty: continue
        
        # 勤務地(T1 or T2)の特定: セル(0,0)付近を解析
        raw_loc_text = str(df.iloc[0, 0])
        work_place = "T2" if "T2" in raw_loc_text else ("T1" if "T1" in raw_loc_text else "Unknown")
        
        # 名前が含まれる行を全探索（セル内改行対応）
        found_indices = []
        for i, row_val in enumerate(df.iloc[:, 0].astype(str)):
            if clean_target in normalize_text(row_val):
                found_indices.append(i)
        
        for idx in found_indices:
            # 自分のシフト行を取得
            my_daily = df.iloc[idx : idx + 1, :].copy().reset_index(drop=True)
            # 他者のデータ（交代相手の特定用）
            others = df.drop([idx]).copy().reset_index(drop=True)
            
            # 勤務地＋名前をキーにして保持
            key = f"{work_place}_{idx}"
            table_dictionary[key] = [my_daily, others, year, month]
            
    return table_dictionary, year, month

def process_full_month(integrated_dic):
    """統合された辞書から全日程のスケジュールを生成"""
    all_final_rows = []
    
    for key, data in integrated_dic.items():
        my_daily, others = data[0], data[1]
        year, month = data[2], data[3]
        time_sched = data[4] if len(data) > 4 else None
        place_label = key.split('_')[0] # T1 or T2
        
        if not year or not month: continue
        num_days = calendar.monthrange(year, month)[1]
        
        # 日付「1」が始まる列を動的に特定
        start_col = -1
        # 最初の数行のどこかに「1」が含まれるセルを探す
        for c in range(1, len(my_daily.columns)):
            # ヘッダー行またはデータ行のセルを確認
            col_data = "".join(my_daily.iloc[:, c].astype(str).tolist())
            if re.search(r'\b1\b', col_data) or "1" in col_data.split('\n'):
                start_col = c
                break
        
        if start_col == -1: 
            # バックアップ：もし特定できなければ2列目からと仮定
            start_col = 1

        for day in range(1, num_days + 1):
            target_date_str = f"{year}-{month:02d}-{day:02d}"
            col_idx = start_col + (day - 1)
            
            if col_idx >= my_daily.shape[1]: continue
            
            raw_cell = str(my_daily.iloc[0, col_idx]).strip()
            if not raw_cell or raw_cell.lower() == 'nan': continue
            
            # シフト記号の抽出（A A などの複数表記や改行に対応）
            shifts = [s.strip() for s in re.split(r'[\s\n,、]+', raw_cell) if s.strip()]
            
            for s_info in shifts:
                if any(k in s_info for k in ["休", "公", "有", "特", "欠", "振", "替"]):
                    all_final_rows.append([f"【{s_info}】", target_date_str, "", target_date_str, "", "True", "休暇", place_label])
                else:
                    all_final_rows.append([f"{place_label}_{s_info}", target_date_str, "", target_date_str, "", "True", "勤務予定", place_label])
                    # 時程表との紐付け（もしあれば）
                    if time_sched is not None:
                        # ここに時程詳細計算ロジック(shift_cal)を挿入
                        pass
                        
    return all_final_rows
