import pandas as pd
import camelot
import unicodedata
import re
import io
import calendar
import streamlit as st
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account

def get_gdrive_service(secrets):
    creds = service_account.Credentials.from_service_account_info(
        secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build('drive', 'v3', credentials=creds)

def normalize_text(text):
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def convert_decimal_to_time(val):
    """0行目の小数(6.25)を時刻(6:15)に変換"""
    try:
        s_val = str(val).strip()
        if not s_val or not re.match(r'^[\d.]+$', s_val):
            return val
        f_val = float(s_val)
        hour = int(f_val)
        minute = int(round((f_val - hour) * 60))
        return f"{hour}:{minute:02d}"
    except:
        return val

def pdf_reader(file_name, df, target_staff):
    """月・曜日の検問とシフト抽出"""
    month_match = re.search(r'(\d{1,2})月', file_name)
    if not month_match:
        st.error("ファイル名から月を特定できません。")
        st.stop()
    
    target_month = int(month_match.group(1))
    year = 2026
    _, last_day = calendar.monthrange(year, target_month)
    expected_first_day = ["月", "火", "水", "木", "金", "土", "日"][calendar.weekday(year, target_month, 1)]

    actual_last_day = pd.to_numeric(df.iloc[0, 1:], errors='coerce').max()
    actual_first_day = str(df.iloc[1, 1]).strip()

    if actual_last_day != last_day or expected_first_day not in actual_first_day:
        st.error(f"⚠️ PDFが{target_month}月の暦（1日={expected_first_day}曜）と一致しません。")
        st.stop()

    location_key = str(df.iloc[0, 0]).strip()
    clean_target = normalize_text(target_staff)
    search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
    
    matched_indices = df.index[search_col == clean_target].tolist()
    if not matched_indices:
        return location_key, None, None

    idx = matched_indices[0]
    return location_key, df.iloc[idx : idx + 2, :].copy(), df.drop([0, idx, idx+1] if idx+1 < len(df) else [0, idx]).copy()

def time_schedule_from_drive(service, file_id):
    """勤務地ごとに時間範囲を特定し、時刻表記に作り変えて抽出"""
    request = service.files().export_media(fileId=file_id, 
        mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done: _, done = downloader.next_chunk()
    fh.seek(0)
    
    full_df = pd.read_excel(fh, header=None, engine='openpyxl', sheet_name=0, dtype=str).fillna('')
    location_rows = full_df[full_df.iloc[:, 0].astype(str).str.strip() != ''].index.tolist()
    location_data_dic = {}
    
    for i, start_row in enumerate(location_rows):
        end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
        location_name = str(full_df.iloc[start_row, 0]).strip()
        temp_range = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
        
        header_row = temp_range.iloc[0, :]
        time_cols = []
        for col_idx in range(3, len(header_row)):
            val = str(header_row.iloc[col_idx]).strip()
            if val != "" and re.match(r'^[\d.]+$', val):
                time_cols.append(col_idx)
            elif time_cols:
                break
        
        selected_cols = [0, 1, 2] + time_cols
        new_df = temp_range.iloc[:, selected_cols].copy()
        for c in range(3, len(new_df.columns)):
            new_df.iloc[0, c] = convert_decimal_to_time(new_df.iloc[0, c])
            
        location_data_dic[location_name] = new_df
    return location_data_dic
