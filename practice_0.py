import streamlit as st
import pandas as pd
import re
import unicodedata
import camelot
from googleapiclient.discovery import build
from google.oauth2 import service_account

# --- 認証 ---
def get_unified_services():
    if "gcp_service_account" in st.secrets:
        info = st.secrets["gcp_service_account"]
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=[
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/spreadsheets.readonly"
            ]
        )
        return build('drive', 'v3', credentials=creds), build('sheets', 'v4', credentials=creds)
    return None, None

def normalize_text(text):
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

# --- 改善：数値(6.25)を時間(6:15)に変換 ---
def convert_float_to_time(val):
    """数値や数値形式の文字列を時間表記に変換する"""
    try:
        f_val = float(val)
        hours = int(f_val)
        minutes = int(round((f_val - hours) * 60))
        return f"{hours}:{minutes:02d}"
    except (ValueError, TypeError):
        return val # 数値でない場合はそのまま返す

def extract_key_from_pdf_val(val):
    text = str(val)
    text = re.sub(r'\d{4}/\d{1,2}/\d{1,2}', '', text)
    text = re.sub(r'\d{1,2}/\d{1,2}', '', text)
    text = re.sub(r'\([月火水木金土日]\)', '', text)
    text = re.sub(r'\d{1,2}:\d{2}', '', text)
    return text.strip()

def parse_info_from_filename(filename):
    month_match = re.search(r'(\d+)月', filename)
    days_in_month = 31
    if month_match:
        m = int(month_match.group(1))
        if m in [4, 6, 9, 11]: days_in_month = 30
        elif m == 2: days_in_month = 28
    day_of_week_match = re.search(r'\(([月火水木金土日])\)', filename)
    expected_dow = day_of_week_match.group(1) if day_of_week_match else None
    return days_in_month, expected_dow

# --- スプレッドシート読み込み ---
def time_schedule_from_drive(sheets_service, file_id):
    spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=file_id).execute()
    sheets = spreadsheet.get('sheets', [])
    location_data_dic = {}
    for s in sheets:
        title = s.get("properties", {}).get("title")
        result = sheets_service.spreadsheets().values().get(spreadsheetId=file_id, range=f"'{title}'!A1:Z300").execute()
        vals = result.get('values', [])
        if not vals: continue
        df = pd.DataFrame(vals).fillna('')
        current_raw_key, start_row = None, 0
        for i in range(len(df)):
            val_a = str(df.iloc[i, 0]).strip()
            if val_a != "":
                if current_raw_key is not None:
                    location_data_dic[current_raw_key] = extract_col_range(df.iloc[start_row:i, :])
                current_raw_key, start_row = val_a, i
        if current_raw_key is not None:
            location_data_dic[current_raw_key] = extract_col_range(df.iloc[start_row:, :])
    return location_data_dic

def extract_col_range(loc_df):
    sample_row = loc_df.iloc[0, :].tolist()
    col_start = 3
    for c in range(3, len(sample_row)):
        if re.match(r'^-?\d+(\.\d+)?$', str(sample_row[c])):
            col_start = c
            break
    col_end = len(sample_row)
    for c in range(col_start, len(sample_row)):
        val = str(sample_row[c]).strip()
        if val != "" and not re.match(r'^-?\d+(\.\d+)?$', val):
            col_end = c
            break
    
    # 抽出範囲を取得
    extracted = pd.concat([loc_df.iloc[:, 0:3], loc_df.iloc[:, col_start:col_end]], axis=1)
    
    # 【改善】時間軸（1行目）の数値を時間表記に変換
    new_columns = list(extracted.columns)
    header = extracted.iloc[0].tolist()
    for i in range(3, len(header)):
        header[i] = convert_float_to_time(header[i])
    extracted.iloc[0] = header
    
    return extracted

# --- メイン解析 ---
def pdf_reader_final(uploaded_file, target_staff, time_dic):
    filename = uploaded_file.name
    clean_target = normalize_text(target_staff)
    expected_days, expected_dow = parse_info_from_filename(filename)
    
    with open("temp.pdf", "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    try:
        tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    except:
        return None, "PDFの読み込みに失敗しました。"

    all_page_results = []
    for table in tables:
        df = table.df
        if df.empty or len(df) < 2: continue
        
        # 整合性チェック（第2関門）
        header_row = df.iloc[0].astype(str).tolist()
        actual_days = sum(1 for cell in header_row if re.search(r'\d+', cell))
        actual_dow = next((re.search(r'([月火水木金土日])', c).group(1) for c in header_row if re.search(r'([月火水木金土日])', c)), None)

        if actual_days != expected_days:
            return None, f"不一致：ファイル名からの期待日数は {expected_days}日ですが、内容には {actual_days}日分のデータしかありません。"
        if expected_dow and actual_dow != expected_dow:
            return None, f"不一致：期待は {expected_dow}曜日開始ですが、内容は {actual_dow}曜日開始です。"

        # 勤務地チェック（第一関門）
        raw_pdf_key = extract_key_from_pdf_val(df.iloc[0, 0])
        matched_raw_key = next((k for k in time_dic.keys() if normalize_text(k) in normalize_text(raw_pdf_key)), None)
        if not matched_raw_key:
            return None, f"勤務地「{raw_pdf_key}」が設定されていません。確認して下さい。"

        # スタッフチェック（第三関門）
        search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
        if clean_target not in search_col.values:
            return None, f"スタフ「{target_staff}」が見つかりません。"

        idx = search_col[search_col == clean_target].index[0]
        all_page_results.append({
            'key': matched_raw_key,
            'my_shift': df.iloc[idx : idx + 2, :].copy(),
            'other_shift': df.drop([idx, idx+1]) if idx+1 < len(df) else df.drop(idx),
            'time_schedule': time_dic[matched_raw_key]
        })
    return all_page_results, None
