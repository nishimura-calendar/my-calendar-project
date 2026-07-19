import streamlit as st
import pandas as pd
import io
import camelot
import calendar
import re
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaIoBaseDownload

# --- [1] 時程表読み込み関連 ---
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
        end_idx = location_indices[i+1] if i+1 < len(location_indices) else df.index[-1] + 1
        schedule = df.iloc[start_idx:end_idx].copy()
        for col_idx in range(3, schedule.shape[1]):
            val = schedule.iloc[0, col_idx]
            try:
                schedule.iloc[0, col_idx] = format_time(val)
            except (ValueError, TypeError):
                break
        location_data[key] = schedule
    return location_data

@st.cache_data
def get_latest_schedule_to_dict():
    # Google API認証とデータ取得
    creds_dict = st.secrets["google_oauth_credentials"]
    creds = Credentials(**creds_dict)
    service = build('drive', 'v3', credentials=creds)
    file_id = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"
    request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    df = pd.read_excel(fh, header=None, engine='openpyxl', dtype=str)
    return process_data(df)

# --- [2] PDFシフト表ファイル読込・判定 ---
def extract_year_month(file_name):
    # ファイル名から年(4桁)と月(数字+"月")を抽出
    year_match = re.search(r'(\d{4})', file_name)
    month_match = re.search(r'(\d{1,2})月', file_name)
    year = int(year_match.group(1)) if year_match else None
    month = int(month_match.group(1)) if month_match else None
    return year, month

def check_pdf_file(file_path, data_dict, file_name):
    # (1) Camelotで読込
    tables = camelot.read_pdf(file_path, pages='all', flavor='stream')
    
    # (2) 第1関門: Key検索
    target_key = None
    for table in tables:
        df = table.df
        for i, row in df.iterrows():
            for key in data_dict.keys():
                if key.replace(" ", "").replace(" ", "").lower() in str(row[0]).replace(" ", "").replace(" ", "").lower():
                    target_key = key
                    break
            if target_key: break
        if target_key: break
    
    if not target_key:
        st.error("勤務地が見当りません。シフト表ではないようです。")
        st.stop()
    
    # (3) 第2関門: 年月取得（入力フォームの条件分岐）
    year, month = extract_year_month(file_name)
    
    if year and month:
        st.success(f"ファイルから年月を特定しました: {year}年{month}月")
    else:
        st.warning("ファイル名から年月を自動取得できませんでした。")
        year = st.number_input("年を入力してください", min_value=2020, max_value=2030, value=2026)
        month = st.number_input("月を入力してください", min_value=1, max_value=12, value=1)
    
    last_day = calendar.monthrange(year, month)[1]
    last_weekday = calendar.weekday(year, month, last_day)
    
    st.write(f"判定結果: {year}年{month}月 (最終日: {last_day}, 最終曜日: {last_weekday})")
    return target_key

# --- メイン処理 ---
st.title("PDFシフト表アップロード")
data_dict = get_latest_schedule_to_dict()
uploaded_file = st.file_uploader("PDFシフト表ファイルをアップロードしてください", type="pdf")

if uploaded_file:
    path = "temp.pdf"
    with open(path, "wb") as f: f.write(uploaded_file.getbuffer())
    key = check_pdf_file(path, data_dict, uploaded_file.name)
    st.write(f"Key: {key} を特定しました。")
