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

# タイムアウト対策：ネットワークフリーズを防ぐ
socket.setdefaulttimeout(10)

SPREADSHEET_ID = '1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE'

# --- 認証とサービス取得 ---
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

# --- 時程表の取得 ---
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
        st.error(f"時程表読込失敗: {e}")
        st.stop()

# --- PDF解析：日付整合性まで ---
def process_pdf_shift(file_path, file_name, time_schedule):
    # 1. PDF読み込み
    try:
        tables = camelot.read_pdf(file_path, pages='all', flavor='stream')
        df = tables[0].df
    except Exception as e:
        st.error(f"PDF読み込みエラー: {e}")
        st.stop()

    # 2. キー行(T1/T2等)の動的把握
    key_idx = None
    target_keys = list(time_schedule.keys())
    for idx, row in df.iterrows():
        row_str = "".join([str(cell) for cell in row]).replace(" ", "").replace(" ", "")
        if any(k in row_str for k in target_keys):
            key_idx = idx
            break
            
    if key_idx is None:
        st.error("シフト表の識別キー(T1/T2等)が見つかりませんでした。")
        st.stop()

    # 3. 最大日付の動的抽出（行番号固定せず、キー行の次から探索）
    search_range = df.iloc[key_idx + 1 : key_idx + 7]
    all_dates = []
    for val in search_range.values.flatten():
        if pd.isna(val): continue
        s_val = str(val).strip()
        # 数値抽出：整数および浮動小数点を考慮
        if s_val.isdigit():
            all_dates.append(int(s_val))
        elif '.' in s_val:
            try:
                all_dates.append(int(float(s_val)))
            except:
                continue
            
    A_last_day = max(all_dates) if all_dates else 0
    
    # 4. ファイル名から年月を取得して整合性チェック
    match = re.search(r'(\d{4})年?(\d{1,2})月', file_name)
    year = int(match.group(1)) if match else datetime.now().year
    month = int(match.group(2)) if match else datetime.now().month
    _, B_last_day = calendar.monthrange(year, month)
    
    if A_last_day != B_last_day:
        st.error(f"データ不一致: PDF内の最終日({A_last_day}日)が{year}年{month}月の末日({B_last_day}日)と一致しません。")
        st.stop()
    
    st.success(f"確認完了: {year}年{month}月シフト表 (最終日:{A_last_day}日)")
    return True

# --- メイン ---
st.title("シフト管理システム")
time_schedule = load_time_schedule()
uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")

if uploaded_file:
    if process_pdf_shift(uploaded_file, uploaded_file.name, time_schedule):
        st.write("整合性確認完了。次のステップへ進みます。")
