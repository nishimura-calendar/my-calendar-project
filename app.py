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

# タイムアウトを10秒に設定（フリーズ防止）
socket.setdefaulttimeout(10)

# 時程表スプレッドシートID
SPREADSHEET_ID = '1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE'

# --- 1. 認証とサービス取得（自動更新機能付き） ---
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
        # トークンが期限切れなら自動更新
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"認証エラー: {e}")
        st.stop()

# --- 2. 時程表の都度読み込み ---
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
        
        # 時程表の読み込みと辞書化
        df = pd.read_excel(fh, sheet_name="Table 1")
        time_schedule = {str(row['シフトコード']): row.to_dict() for _, row in df.iterrows()}
        return time_schedule
    except socket.timeout:
        st.error("通信がタイムアウトしました。再試行してください。")
        st.stop()
    except Exception as e:
        st.error(f"時程表の読み込みに失敗しました: {e}")
        st.stop()

# --- 3. PDF解析（第1関門・第2関門） ---
def process_pdf_shift(file_path, file_name, time_schedule):
    # (1) PDF読込
    try:
        tables = camelot.read_pdf(file_path, pages='all', flavor='stream')
        df = tables[0].df
    except Exception as e:
        st.error(f"PDF解析エラー: {e}")
        st.stop()

    # (2) 第1関門: キー検索
    key_row_idx = None
    target_keys = list(time_schedule.keys())
    for idx, row in df.iterrows():
        cell_val = str(row[0]).replace(" ", "").replace(" ", "")
        if any(k in cell_val for k in target_keys):
            key_row_idx = idx
            break
            
    if key_row_idx is None:
        st.error("シフト表のキーが見当たりません。ファイルを確認して下さい。")
        st.stop()

    # (3) 第2関門: 日付整合性判定
    subset = df.iloc[:key_row_idx + 1]
    dates = [int(val) for val in subset.values.flatten() if str(val).isdigit()]
    A_last_day = max(dates) if dates else 0
    
    match = re.search(r'(\d{4})', file_name)
    year = int(match.group(1)) if match else datetime.now().year
    month_match = re.search(r'(\d{1,2})月', file_name)
    month = int(month_match.group(1)) if month_match else datetime.now().month
    
    _, B_last_day = calendar.monthrange(year, month)
    
    if A_last_day != B_last_day:
        st.error(f"【エラー】不一致: PDF({A_last_day}日) vs ファイル名({B_last_day}日)")
        st.stop()
    
    st.success("整合性確認完了。詳細読込へ進みます。")

# --- 4. メイン ---
st.title("シフト管理システム")

# 順序同期：時程表が読めない限りPDFアップロードを表示しない
time_schedule = load_time_schedule()

uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")
if uploaded_file:
    process_pdf_shift(uploaded_file, uploaded_file.name, time_schedule)
