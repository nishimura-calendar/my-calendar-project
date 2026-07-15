import streamlit as st
import pandas as pd
import io
import camelot
import re
import calendar
from datetime import datetime
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaIoBaseDownload

# --- [1] 時程表読込ロジック ---
def get_service():
    # secretsが正しく設定されているか確認してください
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
    for start_idx in location_indices:
        key = str(df.iloc[start_idx, 0])
        location_data[key] = df.iloc[start_idx:start_idx+10] 
    return location_data

@st.cache_data(ttl=600)
def load_and_process_data():
    service = get_service()
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

# --- [2] PDFチェック関数 ---
def run_first_gate(uploaded_file, data_dict):
    tables = camelot.read_pdf(uploaded_file, pages='all')
    df = tables[0].df
    
    valid_keys = list(data_dict.keys())
    # ① 0列目を検索
    key_found = next((k for k in valid_keys if df.iloc[:, 0].astype(str).str.contains(k).any()), None)
    
    if not key_found:
        st.error(f"「{key_found}」が見当りません。シフト表ではないようです。")
        st.write(df)
        st.stop()
        
    # ② 最終日付・曜日の抽出
    idx = df[df.iloc[:, 0].astype(str).str.contains(key_found)].index[0]
    row_data = " ".join(df.iloc[idx].astype(str))
    dates = [int(n) for n in re.findall(r'\d+', row_data) if 1 <= int(n) <= 31]
    A_date = max(dates) if dates else 0
    days = re.findall(r'[月火水木金土日]', row_data)
    A_day = days[-1] if days else "不明"
    
    # ③ 年月取得
    match = re.search(r'(\d{4}).*?(\d{1,2})月', uploaded_file.name)
    year, month = (int(match.group(1)), int(match.group(2))) if match else (2026, 1)
    
    # ④ 判定用データ生成
    last_day_num = calendar.monthrange(year, month)[1]
    B_day = ["月", "火", "水", "木", "金", "土", "日"][datetime(year, month, last_day_num).weekday()]
    
    # ⑤⑥ 判定
    if A_date == last_day_num and A_day == B_day:
        st.success("ファイルチェックOK")
    else:
        st.error("エラー：ファイル名とシフト表の日付が一致しません")
        st.stop()

# --- メイン ---
st.title("シフトカレンダー登録")
data_dict = load_and_process_data() # ここでエラーが出る場合は上の関数定義を確認
uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")

if uploaded_file:
    run_first_gate(uploaded_file, data_dict)
