import streamlit as st
import pandas as pd
import re
import camelot
import os
from googleapiclient.discovery import build
from google.oauth2 import service_account

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

def convert_float_to_time(val):
    try:
        str_val = str(val).strip()
        if str_val in ["", "なし"]: return ""
        f_val = float(str_val)
        hours = int(f_val)
        minutes = int(round((f_val - hours) * 60))
        return f"{hours}:{minutes:02d}"
    except (ValueError, TypeError):
        return val

# クレンジング関数
def clean_pdf_location_key(val):
    text = str(val).strip()
    text = re.sub(r'\d{4}/\d{1,2}/\d{1,2}', '', text)
    text = re.sub(r'\d{1,2}/\d{1,2}', '', text)
    text = re.sub(r'[\(\[\{][月火水木金土日][\)\}\]]', '', text)
    text = re.sub(r'\d{1,2}:\d{2}', '', text)
    text = re.sub(r'(\s+\d+)+\s*$', '', text)
    text = re.sub(r'^\s*(\d+\s+)+', '', text)
    return text.strip()

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
        current_key, start_row = None, 0
        for i in range(len(df)):
            val_a = str(df.iloc[i, 0]).strip()
            if val_a != "":
                if current_key is not None:
                    location_data_dic[current_key] = extract_col_range(df.iloc[start_row:i, :])
                current_key, start_row = val_a, i
        if current_key is not None:
            location_data_dic[current_key] = extract_col_range(df.iloc[start_row:, :])
    return location_data_dic

def extract_col_range(loc_df):
    if loc_df.empty: return loc_df
    header_row = loc_df.iloc[0].tolist()
    num_pattern = re.compile(r'^-?\d+(\.\d+)?$')
    start_indices = [i for i, val in enumerate(header_row) if i >= 3 and num_pattern.match(str(val).strip())]
    if not start_indices: return loc_df.iloc[:, 0:3]
    col_start, col_end = min(start_indices), len(header_row)
    res_df = pd.concat([loc_df.iloc[:, 0:3], loc_df.iloc[:, col_start:col_end]], axis=1)
    if not res_df.empty:
        new_header = res_df.iloc[0].tolist()
        for i in range(3, len(new_header)):
            new_header[i] = convert_float_to_time(new_header[i])
        res_df.iloc[0] = new_header
    return res_df

# メインの解析ロジック（[0,0]の生データを返すように修正）
def process_pdf_with_preview(pdf_file, target_name, time_dic):
    temp_path = "temp.pdf"
    with open(temp_path, "wb") as f:
        f.write(pdf_file.read())
    try:
        tables = camelot.read_pdf(temp_path, pages='all', flavor='stream')
        if not tables: return None, None, "テーブルを検出できませんでした。"
        
        df = tables[0].df
        raw_val_00 = df.iloc[0, 0] # クレンジング前の生データ
        
        # 1. クレンジング
        new_location = clean_pdf_location_key(raw_val_00)
        
        # 2. Key照合
        matched_key = next((k for k in time_dic.keys() if k in new_location), None)
        
        if not matched_key:
            return raw_val_00, new_location, f"これは『{new_location}』の time_schedule です。まだ時程表マスターに組み込まれていません。"

        # 3. シフト抽出
        df_rows = df.iloc[:, 0].astype(str).tolist()
        if target_name not in df_rows:
            return raw_val_00, new_location, f"スタッフ名『{target_name}』が見つかりません。"
        
        idx = df_rows.index(target_name)
        res = {
            "key": matched_key,
            "my_daily_shift": df.iloc[idx, :].values,
            "other_daily_shift": df.iloc[idx+1, :].values,
            "time_schedule": time_dic[matched_key].iloc[0].values
        }
        return raw_val_00, new_location, res
    finally:
        if os.path.exists(temp_path): os.remove(temp_path)
