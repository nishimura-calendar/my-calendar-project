import streamlit as st
import pandas as pd
import re
import unicodedata
import camelot
import os
from googleapiclient.discovery import build
from google.oauth2 import service_account

# --- 1. 認証サービス (ここがエラーの原因箇所です) ---
def get_unified_services():
    """Google API 認証サービスを構築"""
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

# --- 2. ユーティリティ関数 ---
def normalize_text(text):
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def convert_to_time_string(val):
    if isinstance(val, (int, float)):
        total_minutes = int(round(val * 24 * 60))
        hours = (total_minutes // 60) % 24
        minutes = total_minutes % 60
        return f"{hours:02d}:{minutes:02d}"
    return str(val)

# --- 3. 行列抽出ロジック ---
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
                    location_data_dic[normalize_text(current_key)] = extract_by_key_row(df.iloc[start_row:i, :])
                current_key, start_row = val_a, i
        
        if current_key is not None:
            location_data_dic[normalize_text(current_key)] = extract_by_key_row(df.iloc[start_row:, :])
                
    return location_data_dic

def extract_by_key_row(loc_df):
    """勤務地行（0行目）を基準に時間列を判定し、A-C列と結合"""
    key_row = loc_df.iloc[0, :].tolist()
    col_start, col_end = 3, len(key_row)
    
    for c in range(3, len(key_row)):
        if re.match(r'^-?\d+(\.\d+)?$', str(key_row[c])):
            col_start = c
            break
    for c in range(col_start, len(key_row)):
        val = str(key_row[c]).strip()
        if val != "" and not re.match(r'^-?\d+(\.\d+)?$', val):
            col_end = c
            break
            
    base_info = loc_df.iloc[:, 0:3] # A-C列
    time_data = loc_df.iloc[:, col_start:col_end].copy()
    for col in time_data.columns:
        time_data[col] = time_data[col].apply(convert_to_time_string)
            
    return pd.concat([base_info, time_data], axis=1)

# --- 4. PDF解析 ---
def get_key_and_schedule(pdf_stream, time_dic):
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
    try:
        tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice')
        if not tables: return None
        df = tables[0].df
        raw_val = df.iloc[0, 0]
        # 文字列だけ抽出
        pdf_key = re.sub(r'[\d/:()月火水木金土日]', '', str(raw_val))
        pdf_key = normalize_text(pdf_key)
        
        matched_key = next((k for k in time_dic.keys() if pdf_key in k or k in pdf_key), None)
        if matched_key:
            return {'key': matched_key, 'time_schedule': time_dic[matched_key], 'raw': raw_val}
    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")
    return None
