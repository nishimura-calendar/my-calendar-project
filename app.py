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

# タイムアウト対策
socket.setdefaulttimeout(10)

SPREADSHEET_ID = '1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE'

# --- [1] 認証とサービス取得 ---
def get_service():
    try:
        creds_dict = st.secrets["google_oauth_credentials"]
        creds = Credentials(**creds_dict)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"認証エラー: {e}")
        st.stop()

# --- [2] 時程表の取得 ---
@st.cache_data(ttl=600)
def load_time_schedule():
    try:
        service = get_service()
        request = service.files().export_media(fileId=SPREADSHEET_ID, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        fh = io.BytesIO()
        downloader = googleapiclient.http.MediaIoBaseDownload(fh, request)
        done = False
        while not done: _, done = downloader.next_chunk()
        fh.seek(0)
        df = pd.read_excel(fh, sheet_name="Table 1")
        return {str(row['シフトコード']): row.to_dict() for _, row in df.iterrows()}
    except Exception as e:
        st.error(f"時程表読込失敗: {e}")
        st.stop()

# --- [3] PDF解析と整合性チェック ---
def get_day_name(year, month, day):
    day_names = ["月", "火", "水", "木", "金", "土", "日"]
    return day_names[calendar.weekday(year, month, day)]

def process_pdf_shift(file_path, file_name, time_schedule):
    try:
        tables = camelot.read_pdf(file_path, pages='all', flavor='stream')
        df = pd.concat([t.df for t in tables], ignore_index=True)
    except Exception as e:
        st.error(f"PDF読み込みエラー: {e}")
        st.stop()

    # 日付ヘッダー行の探索
    best_row_idx = None
    max_date_count = 0
    for idx, row in df.iterrows():
        text_row = " ".join([str(val) for val in row])
        nums = re.findall(r'\d+', text_row)
        dates = [int(n) for n in nums if 1 <= int(n) <= 31]
        if len(dates) > max_date_count:
            max_date_count = len(dates)
            best_row_idx = idx
            
    if best_row_idx is None:
        st.error("シフト表の日付ヘッダーが見つかりませんでした。")
        st.stop()

    # 整合性チェック用の値算出
    match = re.search(r'(\d{4})年?(\d{1,2})月', file_name)
    year = int(match.group(1)) if match else datetime.now().year
    month = int(match.group(2)) if match else datetime.now().month

    text_best = " ".join([str(val) for val in df.iloc[best_row_idx]])
    all_dates = [int(n) for n in re.findall(r'\d+', text_best) if 1 <= int(n) <= 31]
    A_last_day = max(all_dates) if all_dates else 0
    A_last_weekday = get_day_name(year, month, A_last_day) if A_last_day > 0 else "不明"

    _, B_last_day = calendar.monthrange(year, month)
    B_last_weekday = get_day_name(year, month, B_last_day)

    # 不一致時のみ警告を表示
    if A_last_day != B_last_day or A_last_weekday != B_last_weekday:
        error_msg = (
            f"### ⚠️ データ不一致が発生しました\n\n"
            f"**【A: PDFファイル内容から抽出】**\n- 最終日: {A_last_day}日 / 曜日: {A_last_weekday}\n\n"
            f"**【B: ファイル名から算出】**\n- 最終日: {B_last_day}日 / 曜日: {B_last_weekday}\n\n"
            f"PDFのレイアウトが正しく読み取れていない可能性があります。"
        )
        st.error(error_msg)
        with open(file_path, "rb") as f:
            st.download_button("PDFをダウンロードして確認", f, file_name=file_name)
        st.stop()
    
    st.success(f"確認完了: {year}年{month}月 (最終日:{A_last_day}日)")
    return True

# --- [4] メイン処理 ---
st.title("シフト管理システム")
time_schedule = load_time_schedule()
uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")

if uploaded_file:
    with open("temp_pdf.pdf", "wb") as f:
        f.write(uploaded_file.getbuffer())
    if process_pdf_shift("temp_pdf.pdf", uploaded_file.name, time_schedule):
        st.write("正常に読み込まれました。詳細読込処理へ進みます。")
