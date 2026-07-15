import streamlit as st
import pandas as pd
import io
import camelot
import re
import calendar
from datetime import datetime
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# --- 既存の関数 ---
def get_service():
    creds_dict = st.secrets["google_oauth_credentials"]
    creds = Credentials(**creds_dict)
    return build('drive', 'v3', credentials=creds)

def format_time(val):
    try:
        f_val = float(val)
        h = int(f_val)
        m = int(round((f_val - h) * 60))
        return f"{h}:{m:02d}"
    except (ValueError, TypeError):
        return val

def process_data(df):
    location_data = {}
    location_indices = df[df.iloc[:, 0].notna()].index.tolist()
    for i, start_idx in enumerate(location_indices):
        key = str(df.iloc[start_idx, 0])
        location_data[key] = df.iloc[start_idx:start_idx+10] # 例
    return location_data

@st.cache_data(ttl=600)
def load_and_process_data():
    service = get_service()
    file_id = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"
    request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    downloader.next_chunk()
    fh.seek(0)
    df = pd.read_excel(fh, header=None, dtype=str)
    return process_data(df)

# --- 新規追加：第1関門チェック用関数 ---
def get_pdf_last_date_info(df):
    for i in range(len(df)):
        row_text = " ".join(df.iloc[i].astype(str))
        if re.search(r'\d+', row_text) and re.search(r'[月火水木金土日]', row_text):
            dates = [int(n) for n in re.findall(r'\d+', row_text) if 1 <= int(n) <= 31]
            if dates:
                last_date = max(dates)
                # 該当行から曜日を探す簡易ロジック
                day_match = re.search(r'([月火水木金土日])', row_text)
                return last_date, (day_match.group(1) if day_match else "不明")
    return None, None

# --- メイン処理 ---
st.title("シフトカレンダー登録")
data_dict = load_and_process_data()

uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")

if uploaded_file:
    # 1. PDF読み込み
    tables = camelot.read_pdf(uploaded_file, pages='all')
    df = tables[0].df
    
    # 2. 第1関門① キー検索
    valid_keys = list(data_dict.keys())
    key_found = next((k for k in valid_keys if df.iloc[:, 0].astype(str).str.contains(k).any()), None)
    
    if not key_found:
        st.error(f"「{valid_keys}」が見当たりません。シフト表ではないようです。")
        st.write(df)
        st.stop()
        
    # 3. 日付チェック
    A_date, A_day = get_pdf_last_date_info(df)
    match = re.search(r'(\d{4}).*?(\d{1,2})月', uploaded_file.name)
    if match:
        year, month = int(match.group(1)), int(match.group(2))
        last_day_num = calendar.monthrange(year, month)[1]
        
        # 簡易的な曜日判定（手順B）
        days = ["月", "火", "水", "木", "金", "土", "日"]
        B_day = days[datetime(year, month, last_day_num).weekday()]
        
        if A_date != last_day_num:
            st.error("日付不一致")
            st.write(f"【PDF】{A_date}日、{A_day}曜日 vs 【ファイル名】{last_day_num}日、{B_day}曜日")
            st.write(df)
            st.stop()
            
    st.success("チェックOK")
