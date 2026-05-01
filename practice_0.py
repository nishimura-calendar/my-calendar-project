import streamlit as st
import pandas as pd
import re
import unicodedata
import camelot
import os
from googleapiclient.discovery import build
from google.oauth2 import service_account

# --- 1. 認証サービス構築 ---
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

# --- 2. テキスト正規化 ---
def normalize_text(text):
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def clean_key_from_pdf_val(val):
    """[0,0]から拠点名(T2等)だけを抽出"""
    text = str(val)
    text = re.sub(r'\d{4}/\d{1,2}/\d{1,2}', '', text) # 日付削除
    text = re.sub(r'\([月火水木金土日]\)', '', text)   # 曜日削除
    text = re.sub(r'\d{1,2}:\d{2}', '', text)         # 時刻削除
    return normalize_text(text)

# --- 3. 時程マスター読込 (A列=Key, D列以降=時程) ---
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
                    location_data_dic[normalize_text(current_key)] = df.iloc[start_row:i, 3:] # D列以降
                current_key, start_row = val_a, i
        
        if current_key is not None:
            location_data_dic[normalize_text(current_key)] = df.iloc[start_row:, 3:]
                
    return location_data_dic

# --- 4. PDFからKeyを特定し時程を紐付け ---
def get_key_and_schedule(pdf_stream, time_dic):
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    try:
        tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice')
        if not tables: return None
        df = tables[0].df
        
        # 座標 [0,0] からPDF側のKeyを取得
        pdf_key = clean_key_from_pdf_val(df.iloc[0, 0])
        
        # マスターのKeyと照合（部分一致対応）
        matched_key = next((k for k in time_dic.keys() if pdf_key in k or k in pdf_key), None)
        
        if matched_key:
            return {
                'key': matched_key,
                'time_schedule': time_dic[matched_key],
                'raw_pdf_val': df.iloc[0, 0]
            }
    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")
    return None
