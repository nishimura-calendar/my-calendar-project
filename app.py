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

# --- [3] PDF解析：ヘッダー行探索による末日特定 ---
def process_pdf_shift(file_path, file_name, time_schedule):
    # 1. PDF読み込み：全テーブルを結合
    try:
        tables = camelot.read_pdf(file_path, pages='all', flavor='stream')
        df = pd.concat([t.df for t in tables], ignore_index=True)
    except Exception as e:
        st.error(f"PDF読み込みエラー: {e}")
        st.stop()

    # 2. ★日付ヘッダー行の探索（もっとも日付数字を多く含む行を探す）
    best_row_idx = None
    max_date_count = 0
    
    for idx, row in df.iterrows():
        # 行内の全セルを連結して数字を抽出
        text_row = " ".join([str(val) for val in row])
        nums = re.findall(r'\d+', text_row)
        # 1〜31の範囲内の数値のみを日付としてカウント
        dates = [int(n) for n in nums if 1 <= int(n) <= 31]
        
        # 日付が5つ以上含まれる行をヘッダーの候補とする
        if len(dates) > max_date_count:
            max_date_count = len(dates)
            best_row_idx = idx
            
    if best_row_idx is None:
        st.error("シフト表の日付ヘッダーが見つかりませんでした。")
        st.stop()

    # 3. 見つかったヘッダー行から最大値(末日)を取得
    text_best = " ".join([str(val) for val in df.iloc[best_row_idx]])
    all_dates = [int(n) for n in re.findall(r'\d+', text_best) if 1 <= int(n) <= 31]
    A_last_day = max(all_dates) if all_dates else 0
    
    # 4. ファイル名から年月を取得して整合性チェック
    match = re.search(r'(\d{4})年?(\d{1,2})月', file_name)
    year = int(match.group(1)) if match else datetime.now().year
    month = int(match.group(2)) if match else datetime.now().month
    _, B_last_day = calendar.monthrange(year, month)
    
    if A_last_day != B_last_day:
        st.error(f"データ不一致: PDF最終日({A_last_day}日)が{month}月の末日({B_last_day}日)と一致しません。")
        st.stop()
    
    st.success(f"確認完了: {year}年{month}月 (最終日:{A_last_day}日)")
    return True

# --- [4] メイン処理 ---
st.title("シフト管理システム")
time_schedule = load_time_schedule()
uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")

if uploaded_file:
    if process_pdf_shift(uploaded_file, uploaded_file.name, time_schedule):
        st.write("正常に読み込まれました。詳細読込処理へ進みます。")
