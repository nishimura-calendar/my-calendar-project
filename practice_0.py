import streamlit as st
import pandas as pd
import re
import unicodedata
import camelot
from googleapiclient.discovery import build
from google.oauth2 import service_account

# --- 認証とテキスト処理（既存通り） ---
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

# --- 【追加】時間表記変換ロジック ---
def convert_float_to_time(val):
    """6.25 -> 6:15 への変換"""
    try:
        f_val = float(val)
        hours = int(f_val)
        minutes = int(round((f_val - hours) * 60))
        return f"{hours}:{minutes:02d}"
    except:
        return val

def clean_key_from_pdf_val(val):
    text = str(val)
    text = re.sub(r'\d{4}/\d{1,2}/\d{1,2}', '', text)
    text = re.sub(r'\d{1,2}/\d{1,2}', '', text)
    text = re.sub(r'\([月火水木金土日]\)', '', text)
    text = re.sub(r'\d{1,2}:\d{2}', '', text)
    return text.strip()

# --- 時程表の読み込み ---
def time_schedule_from_drive(sheets_service, file_id):
    spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=file_id).execute()
    sheets = spreadsheet.get('sheets', [])
    location_data_dic = {}

    for s in sheets:
        title = s.get("properties", {}).get("title")
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=file_id, range=f"'{title}'!A1:Z300").execute()
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
            
    res_df = pd.concat([loc_df.iloc[:, 0:3], loc_df.iloc[:, col_start:col_end]], axis=1)
    
    # 【追加】時間軸（1行目）の数値を時間表記に上書き
    if not res_df.empty:
        header = res_df.iloc[0].tolist()
        new_header = [convert_float_to_time(h) if i >= 3 else h for i, h in enumerate(header)]
        res_df.iloc[0] = new_header
    return res_df

# --- PDF解析 (第2関門等を含む) ---
def pdf_reader_final(uploaded_file, target_staff, time_dic):
    # (前回提示のロジックをそのまま使用)
    filename = uploaded_file.name
    clean_target = normalize_text(target_staff)
    
    # 第2関門：月の日数推測
    month_match = re.search(r'(\d+)月', filename)
    expected_days = 31 if month_match and int(month_match.group(1)) in [1,3,5,7,8,10,12] else 30
    
    with open("temp.pdf", "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    try:
        tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    except: return None, "PDF解析失敗"

    final_results = []
    for table in tables:
        df = table.df
        if df.empty or len(df) < 2: continue
        
        # 第2関門：整合性チェック
        header_row = df.iloc[0].astype(str).tolist()
        actual_days = sum(1 for c in header_row if re.search(r'\d+', c))
        if actual_days != expected_days:
            return None, f"不一致：ファイル名は{expected_days}日ですが、中身は{actual_days}日です。"

        # 第1関門：勤務地チェック
        raw_pdf_key = clean_key_from_pdf_val(df.iloc[0, 0])
        matched_key = next((k for k in time_dic.keys() if normalize_text(k) in normalize_text(raw_pdf_key)), None)
        if not matched_key:
            return None, f"勤務地「{raw_pdf_key}」が設定されていません。"

        # 第3関門：スタッフチェック
        search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
        if clean_target not in search_col.values:
            return None, f"スタフ「{target_staff}」が見つかりません。"

        idx = search_col[search_col == clean_target].index[0]
        final_results.append({
            'key': matched_key,
            'my_data': df.iloc[idx : idx + 2, :].copy(),
            'time_range': time_dic[matched_key]
        })
    return final_results, None
