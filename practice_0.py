import pandas as pd
import camelot
import unicodedata
import re
import io
import calendar
import pdfplumber
import datetime
from googleapiclient.discovery import build
from google.oauth2 import service_account

# --- ユーティリティ関数 ---

def extract_year_month_from_text(text):
    """PDF内のテキストから年月を抽出する"""
    if not text: return None, None
    text = unicodedata.normalize('NFKC', text)
    year_match = re.search(r'(202\d)', text)
    month_match = re.search(r'(\d{1,2})月', text)
    
    y = int(year_match.group(1)) if year_match else datetime.datetime.now().year
    m = int(month_match.group(1)) if month_match else None
    
    if m is None:
        date_stamp = re.search(r'202\d[/\- ](\d{1,2})[/\- ]', text)
        if date_stamp: m = int(date_stamp.group(1))
            
    return y, m

def normalize_text(text):
    """テキストから空白・改行を除去"""
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
    戻り値: (テーブル辞書, 解析された年, 解析された月)
    """
    clean_target = normalize_text(target_staff)
    pdf_stream.seek(0)
    
    with open("temp.pdf", "wb") as f: f.write(pdf_stream.getbuffer())
    
    # 年月の特定
    with pdfplumber.open("temp.pdf") as pdf:
        full_text = "\n".join([p.extract_text() or "" for p in pdf.pages])
        year, month = extract_year_month_from_text(full_text)

    # テーブル抽出
    try:
        tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
        if len(tables) == 0:
            tables = camelot.read_pdf("temp.pdf", pages='all', flavor='stream')
    except: return {}, year, month
    
    table_dictionary = {}
    for i, table in enumerate(tables):
        df = table.df
        if df.empty: continue
        
        raw_loc_text = str(df.iloc[0, 0])
        work_place = "T2" if "T2" in raw_loc_text else ("T1" if "T1" in raw_loc_text else f"LOC_{i}")
        
        found_indices = []
        for row_idx, row_val in enumerate(df.iloc[:, 0].astype(str)):
            if clean_target in normalize_text(row_val):
                found_indices.append(row_idx)
        
        for f_idx in found_indices:
            my_daily = df.iloc[f_idx : f_idx + 1, :].copy().reset_index(drop=True)
            others = df.drop([f_idx]).copy().reset_index(drop=True)
            
            key = f"{work_place}_{f_idx}"
            table_dictionary[key] = [my_daily, others, year, month]
            
    return table_dictionary, year, month

def process_full_month(integrated_dic):
    """
    統合されたデータからGoogleカレンダー用フォーマットを生成。
    日数は各データの year, month から自動計算。
    """
    all_final_rows = []
    
    for key, data in integrated_dic.items():
        my_daily, others, year, month = data[0], data[1], data[2], data[3]
        place_label = key.split('_')[0]
        
        if not year or not month: continue
        num_days = calendar.monthrange(year, month)[1] # 月の日数を自動取得
        
        # 日付「1」の列を特定
        start_col = -1
        for c in range(1, len(my_daily.columns)):
            col_content = "".join(my_daily.iloc[:, c].astype(str).tolist())
            if re.search(r'\b1\b', col_content):
                start_col = c
                break
        
        if start_col == -1: start_col = 1

        for day in range(1, num_days + 1):
            target_date_str = f"{year}-{month:02d}-{day:02d}"
            col_idx = start_col + (day - 1)
            
            if col_idx >= my_daily.shape[1]: continue
            
            raw_cell = str(my_daily.iloc[0, col_idx]).strip()
            if not raw_cell or raw_cell.lower() == 'nan': continue
            
            shifts = [s.strip() for s in re.split(r'[\s\n,、]+', raw_cell) if s.strip()]
            
            for s_info in shifts:
                if any(k in s_info for k in ["休", "公", "有", "特", "欠", "振", "替"]):
                    all_final_rows.append([f"【{s_info}】", target_date_str, "", target_date_str, "", "True", "休暇", place_label])
                else:
                    # ここに時程表(time_dic)がある場合は詳細を展開するロジックが入る
                    all_final_rows.append([f"{place_label}_{s_info}", target_date_str, "", target_date_str, "", "True", "勤務予定", place_label])
                        
    return all_final_rows
