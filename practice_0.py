import pandas as pd
import camelot
import unicodedata
import re
import io
import calendar
import pdfplumber
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload

# --- 共通ユーティリティ (consideration_0.py準拠) ---
def normalize_text(text):
    if not isinstance(text, str): return ""
    # 改行・空白をすべて除去して正規化
    return re.sub(r'[\s　\n\r]', '', unicodedata.normalize('NFKC', text)).lower()

def extract_year_month_from_text(text):
    """ファイル名から年月を特定する基本ロジック"""
    if not text: return None, None
    text = unicodedata.normalize('NFKC', text)
    clean_text = re.sub(r'\s+', '', text)
    y_val, m_val = None, None
    
    # 月の特定
    month_match = re.search(r'(\d{1,2})月', clean_text)
    if month_match:
        m_val = int(month_match.group(1))
    
    # 年の特定
    nums = re.findall(r'\d+', clean_text)
    for n in nums:
        val = int(n)
        if len(n) == 4:
            y_val = val
            break
        elif len(n) == 2 and y_val is None:
            y_val = 2000 + val
            
    return y_val, m_val

# --- PDF解析 (決めごとを100%遵守) ---
def pdf_reader(pdf_stream, target_staff, file_name=""):
    """
    1. ファイル名を正とする
    2. 勤務地セルの行から日付・曜日を取る
    3. 自分2行・他人1行
    返り値は [table_dictionary, year, month] の3つとする（app.pyの期待値に合わせる）
    """
    clean_target = normalize_text(target_staff)
    pdf_stream.seek(0)
    temp_path = "temp_process.pdf"
    with open(temp_path, "wb") as f: f.write(pdf_stream.getbuffer())
    
    # ファイル名から年月を取得（基本の決めごと）
    year, month = extract_year_month_from_text(file_name)
    
    # カレンダーの正解を計算
    if year and month:
        first_wday_idx, last_day = calendar.monthrange(year, month)
        weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
        expected_first_wday = weekdays_jp[first_wday_idx]
    else:
        # 年月が不明な場合は空で返す
        return {}, year, month

    try:
        # Camelotによる解析
        tables = camelot.read_pdf(temp_path, pages='all', flavor='lattice')
    except:
        return {}, year, month

    table_dictionary = {}
    
    for table in tables:
        df = table.df
        if df.empty: continue
        
        # --- 勤務地と日付の抽出（決めごと：0行目から取る） ---
        # 勤務地名
        header_raw = str(df.iloc[0, 0])
        header_lines = header_raw.splitlines()
        work_place = header_lines[len(header_lines)//2].strip() if header_lines else "Unknown"
        
        # 日付・曜日
        pdf_days = []
        for col in range(1, df.shape[1]):
            val = normalize_text(str(df.iloc[0, col]))
            d_m = re.search(r'(\d+)', val)
            w_m = re.search(r'([月火水木金土日])', val)
            if d_m and w_m:
                pdf_days.append({"d": int(d_m.group(1)), "w": w_m.group(1)})
        
        # 整合性チェック（合わない表はスキップ）
        if not pdf_days: continue
        if pdf_days[-1]["d"] != last_day: continue
        if pdf_days[0]["w"] != expected_first_wday: continue

        # --- 名前検索と行抽出（決めごと：自分2行、他人1行） ---
        search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
        matched_indices = [i for i, v in enumerate(search_col) if clean_target in v]
        
        if matched_indices:
            idx = matched_indices[0]
            # 自分は2行
            my_daily = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
            # 他人は1行（ヘッダー0行目と自分を除外）
            others = df.drop([0, idx, idx+1] if idx+1 < len(df) else [0, idx]).copy().reset_index(drop=True)
            
            table_dictionary[work_place] = [my_daily, others]
                
    return table_dictionary, year, month

# --- Google Drive 連携 (時程表取得) ---
def time_schedule_from_drive(service, spreadsheet_id):
    """
    Google Drive上のスプレッドシートから時程表データを取得する
    """
    try:
        # シートIDからデータをエクスポートして読み込む処理（consideration_0.py準拠）
        # ※ここでは構造の維持のため概略のみ記述します
        drive_service = service # app.pyから渡されるserviceオブジェクトを使用
        request = drive_service.files().export_media(fileId=spreadsheet_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        fh.seek(0)
        
        # 最初のシートを読み込む
        full_df = pd.read_excel(fh, header=None, engine='openpyxl')
        return full_df.fillna('')
    except:
        return pd.DataFrame()
