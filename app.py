import streamlit as st
import pandas as pd
import io
import camelot
import calendar
import re
import socket
from datetime import datetime
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import googleapiclient.http

# タイムアウトを10秒に設定
socket.setdefaulttimeout(10)

SPREADSHEET_ID = '1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE'

# --- [1] 時程表読み込み ---
def get_service():
    try:
        creds_dict = st.secrets["google_oauth_credentials"]
        creds = Credentials(
            token=creds_dict["token"],
            refresh_token=creds_dict["refresh_token"],
            token_uri=creds_dict["token_uri"],
            client_id=creds_dict["client_id"],
            client_secret=creds_dict["client_secret"]
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"認証エラー: {e}")
        st.stop()

@st.cache_data(ttl=600)
def load_time_schedule():
    try:
        service = get_service()
        request = service.files().export_media(
            fileId=SPREADSHEET_ID, 
            mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        fh = io.BytesIO()
        downloader = googleapiclient.http.MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        fh.seek(0)
        df = pd.read_excel(fh, sheet_name="Table 1")
        return {str(row['シフトコード']): row.to_dict() for _, row in df.iterrows()}
    except Exception as e:
        st.error(f"時程表読込エラー: {e}")
        st.stop()

# --- [2] PDFシフト表ファイル読込 ---
def process_pdf_shift(file_path, file_name, time_schedule):
    # (1) camelotを使用して読込
    try:
        tables = camelot.read_pdf(file_path, pages='all', flavor='stream')
        df = tables[0].df
    except Exception as e:
        st.error(f"PDF解析失敗: {e}")
        st.stop()

    # (2) 第1関門: キー検索
    key_row_idx = None
    target_keys = list(time_schedule.keys())
    for idx, row in df.iterrows():
        row_str = "".join([str(cell) for cell in row]).replace(" ", "").replace(" ", "")
        if any(k in row_str for k in target_keys):
            key_row_idx = idx
            break
            
    if key_row_idx is None:
        st.error("シフト表のキーが見当たりません。")
        st.stop()

    # (3) 第2関門: 日付整合性判定
    # キー行の直後から5行分を日付探索範囲とする
    search_range = df.iloc[key_row_idx+1 : key_row_idx+6]
    
    # 修正：純粋な数字のみを安全に抽出
    all_dates = []
    for val in search_range.values.flatten():
        s_val = str(val).strip()
        if s_val.isdigit():
            all_dates.append(int(s_val))
            
    A_last_day = max(all_dates) if all_dates else 0
    
    # ファイル名から年月を取得
    match = re.search(r'(\d{4})年?(\d{1,2})月', file_name)
    year = int(match.group(1)) if match else datetime.now().year
    month = int(match.group(2)) if match else datetime.now().month
    
    _, B_last_day = calendar.monthrange(year, month)
    
    if A_last_day != B_last_day:
        st.error(f"データ不一致: PDF最終日 {A_last_day}日 vs ファイル設定 {B_last_day}日")
        st.stop()
    
    st.success("整合性確認完了")
    return True

# --- メイン処理 ---
st.title("シフト管理システム")
time_schedule = load_time_schedule()
uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")

if uploaded_file:
    if process_pdf_shift(uploaded_file, uploaded_file.name, time_schedule):
        st.write("詳細読込処理へ進みます...")
