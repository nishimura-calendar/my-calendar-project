import streamlit as st
import pandas as pd
import re
import unicodedata
import camelot
import os
from googleapiclient.discovery import build
from google.oauth2 import service_account

# --- 1. 認証サービス（エラー対策版） ---
def get_unified_services():
    info = None
    if "gcp_service_account" in st.secrets:
        info = st.secrets["gcp_service_account"]
    elif "private_key" in st.secrets:
        info = dict(st.secrets)
    
    if info is None:
        return None, None

    try:
        service_account_info = dict(info)
        creds = service_account.Credentials.from_service_account_info(
            service_account_info, 
            scopes=[
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/spreadsheets.readonly"
            ]
        )
        return build('drive', 'v3', credentials=creds), build('sheets', 'v4', credentials=creds)
    except Exception:
        return None, None

# --- 2. クリーニング・変換コアロジック ---
def normalize_text(text):
    """大文字小文字・スペースを無視するための正規化"""
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def clean_strictly(text):
    """[0,0]専用：日付(1-31)と曜日を狙い撃ちで排除"""
    if not isinstance(text, str): return ""
    # 独立した数字（日付 1-31）のみを削除（\bでT2の2は保護）
    text = re.sub(r'\b([1-9]|[12][0-9]|3[01])\b', '', text)
    # 曜日・記号・空白を排除
    text = re.sub(r'[月火水木金土日()/:：\s　\n]', '', text)
    return normalize_text(text)

def convert_num_to_time_str(val):
    """0.25単位を15分間隔の時刻に変換 (6.25 -> 06:15)"""
    try:
        if isinstance(val, (int, float)) or (isinstance(val, str) and re.match(r'^\d+(\.\d+)?$', val)):
            num = float(val)
            hours = int(num)
            minutes = int(round((num - hours) * 60))
            return f"{hours:02d}:{minutes:02d}"
        return str(val)
    except:
        return str(val)

# --- 3. 時程表（Google Sheets）の取得 ---
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
        current_key, start_row = None, 0
        for i in range(len(df)):
            val_a = str(df.iloc[i, 0]).strip()
            if val_a != "":
                if current_key is not None:
                    # Keyを正規化して保存
                    location_data_dic[normalize_text(current_key)] = extract_structured_data(df.iloc[start_row:i, :])
                current_key, start_row = val_a, i
        if current_key is not None:
            location_data_dic[normalize_text(current_key)] = extract_structured_data(df.iloc[start_row:, :])
    return location_data_dic

def extract_structured_data(loc_df):
    """見出し行（0行目）のみ時刻変換、B列（コード）は維持"""
    if loc_df.empty: return loc_df
    key_row = loc_df.iloc[0, :].tolist()
    col_start = None
    for c in range(3, len(key_row)):
        if re.match(r'^\d+(\.\d+)?$', str(key_row[c]).strip()):
            col_start = c
            break
    if col_start is None: return loc_df.iloc[:, 0:3]

    base_info = loc_df.iloc[:, 0:3].copy()
    time_data = loc_df.iloc[:, col_start:].copy()

    # 勤務地行(0行目)のみ変換
    for col in time_data.columns:
        val_top = time_data.iloc[0].loc[col]
        time_data.iloc[0, time_data.columns.get_loc(col)] = convert_num_to_time_str(val_top)
    return pd.concat([base_info, time_data], axis=1)

# --- 4. PDF [0,0] セル判定 ---
def scan_pdf_0_0_only(pdf_stream, time_dic):
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
    try:
        tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice')
        if not tables: return [], pd.DataFrame([{"エラー": "表未検出"}])
        
        raw_val = str(tables[0].df.iloc[0, 0])
        cleaned_val = clean_strictly(raw_val)
        
        found_results = []
        if cleaned_val in time_dic:
            found_results.append({'key': cleaned_val, 'time_schedule': time_dic[cleaned_val]})
            status = f"○ 一致 ({cleaned_val})"
        else:
            status = f"× 不一致 ('{cleaned_val}')"

        report_df = pd.DataFrame([{"対象": "[0,0]", "生データ": raw_val[:30]+"...", "排除後": cleaned_val, "判定": status}])
        return found_results, report_df
    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")
