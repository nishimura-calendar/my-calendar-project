import streamlit as st
import pandas as pd
import re
import unicodedata
import camelot
from googleapiclient.discovery import build
from google.oauth2 import service_account

def get_unified_services():
    """app.pyの6行目で呼び出されている認証関数"""
    if "gcp_service_account" in st.secrets:
        info = st.secrets["gcp_service_account"]
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=[
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/spreadsheets.readonly"
            ]
        )
        # DriveサービスとSheetsサービスを順番に返す
        return build('drive', 'v3', credentials=creds), build('sheets', 'v4', credentials=creds)
    return None, None

def normalize_text(text):
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def clean_key_from_pdf_val(val):
    """PDF座標[0,0]からKeyを抽出"""
    text = str(val)
    text = re.sub(r'\d{4}/\d{1,2}/\d{1,2}', '', text) # 日付除去
    text = re.sub(r'\([月火水木金土日]\)', '', text)  # 曜日除去
    text = re.sub(r'\d{1,2}:\d{2}', '', text)         # 時刻除去
    return normalize_text(text)

def time_schedule_from_drive(sheets_service, file_id):
    """A列をKeyとして行列範囲を特定するロジック"""
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
        current_key = None
        start_row = 0
        
        for i in range(len(df)):
            val_a = str(df.iloc[i, 0]).strip()
            if val_a != "":
                if current_key is not None:
                    location_data_dic[normalize_text(current_key)] = extract_col_range(df.iloc[start_row:i, :])
                current_key = val_a
                start_row = i
        
        if current_key is not None:
            location_data_dic[normalize_text(current_key)] = extract_col_range(df.iloc[start_row:, :])
                
    return location_data_dic

def extract_col_range(loc_df):
    """D列以降の数値〜文字列の列範囲特定"""
    sample_row = loc_df.iloc[0, :].tolist()
    col_start = 3
    col_end = len(sample_row)
    for c in range(3, len(sample_row)):
        if re.match(r'^-?\d+(\.\d+)?$', str(sample_row[c])):
            col_start = c
            break
    for c in range(col_start, len(sample_row)):
        val = str(sample_row[c]).strip()
        if val != "" and not re.match(r'^-?\d+(\.\d+)?$', val):
            col_end = c
            break
    return pd.concat([loc_df.iloc[:, 0:3], loc_df.iloc[:, col_start:col_end]], axis=1)

def pdf_reader_with_logic_7(pdf_stream, target_staff, time_dic):
    """座標[0,0],[0,1],[1,1]による判定ロジック"""
    clean_target = normalize_text(target_staff)
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    try:
        tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    except: return []

    final_results = []
    for table in tables:
        df = table.df
        if df.empty or len(df) < 2: continue
        
        # 座標による位置決め
        val_00 = df.iloc[0, 0]
        pdf_key = clean_key_from_pdf_val(val_00)
        
        search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
        if clean_target in search_col.values:
            idx = search_col[search_col == clean_target].index[0]
            my_data = df.iloc[idx : idx + 2, :].copy()
            
            # Key照合（第三関門）
            matched_key = next((k for k in time_dic.keys() if k in pdf_key or pdf_key in k), None)
            
            if matched_key:
                final_results.append({
                    'key': matched_key,
                    'coords': {"[0,0]": val_00, "[0,1]": df.iloc[0, 1], "[1,1]": df.iloc[1, 1]},
                    'my_data': my_data,
                    'time_range': time_dic[matched_key]
                })
    return final_results
