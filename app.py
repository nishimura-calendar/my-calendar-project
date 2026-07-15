import streamlit as st
import pandas as pd
import io
import re
import camelot
import unicodedata
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# --- 1. 関数定義セクション ---
def get_service():
    creds_dict = st.secrets["google_oauth_credentials"]
    creds = Credentials(
        token=creds_dict["token"],
        refresh_token=creds_dict["refresh_token"],
        token_uri=creds_dict["token_uri"],
        client_id=creds_dict["client_id"],
        client_secret=creds_dict["client_secret"]
    )
    return build('drive', 'v3', credentials=creds)

def format_time(val):
    try:
        f_val = float(val)
        h = int(f_val)
        m = int(round((f_val - h) * 60))
        return f"{h}:{m:02d}"
    except (ValueError, TypeError):
        return val

@st.cache_data(ttl=600)
def load_time_schedule_data():
    service = get_service()
    file_id = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"
    request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done: _, done = downloader.next_chunk()
    fh.seek(0)
    
    df = pd.read_excel(fh, header=None, engine='openpyxl', dtype=str)
    
    location_data = {}
    indices = df[df.iloc[:, 0].notna()].index.tolist()
    for i, start_idx in enumerate(indices):
        key = str(df.iloc[start_idx, 0])
        end_idx = indices[i+1] if i+1 < len(indices) else len(df)
        schedule = df.iloc[start_idx:end_idx].copy()
        
        for col_idx in range(3, len(schedule.columns)):
            val = schedule.iloc[0, col_idx]
            try:
                float(val)
                schedule.iloc[0, col_idx] = format_time(val)
            except (ValueError, TypeError):
                break
        location_data[key] = schedule
    return location_data

# --- 2. メイン処理セクション ---
st.title("シフトカレンダー管理システム")

# [1] 時程表読み込み
try:
    time_schedules = load_time_schedule_data()
    st.sidebar.success("時程表の読み込み完了")
except Exception as e:
    st.error(f"時程表の読み込みでエラーが発生しました: {e}")
    st.stop()

# [2] PDFアップロード以降の処理...
