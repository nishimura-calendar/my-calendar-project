import streamlit as st
import pandas as pd
import io
import camelot
import tempfile
import os
import re
import calendar
from datetime import datetime
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# --- [1] 時程表読込ロジック (添付ファイル参照) ---
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
        key = str(df.iloc[start_idx, 0]).strip()
        end_idx = location_indices[i+1] if i+1 < len(location_indices) else df.index[-1] + 1
        schedule = df.iloc[start_idx:end_idx].copy()
        for col_idx in range(3, schedule.shape[1]):
            val = schedule.iloc[0, col_idx]
            try:
                f_val = float(val)
                schedule.iloc[0, col_idx] = format_time(f_val)
            except (ValueError, TypeError):
                schedule = schedule.iloc[:, :col_idx]
                break
        location_data[key] = schedule
    return location_data

@st.cache_data(ttl=600)
def load_time_schedule():
    # 認証情報は Streamlit Secrets に保存している前提
    creds_dict = st.secrets["google_oauth_credentials"]
    creds = Credentials(**creds_dict)
    service = build('drive', 'v3', credentials=creds)
    file_id = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"
    request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done: _, done = downloader.next_chunk()
    fh.seek(0)
    df = pd.read_excel(fh, header=None, engine='openpyxl', dtype=str)
    return process_data(df)

# --- [2] 共通関数 (年月取得・算出) ---
def get_year_month_from_filename(filename):
    year_match = re.search(r'(\d{4})', filename)
    month_match = re.search(r'(\d{1,2})月', filename)
    return (int(year_match.group(1)) if year_match else None, 
            int(month_match.group(1)) if month_match else None)

def calculate_last_date_info(year, month):
    _, last_day = calendar.monthrange(year, month)
    last_weekday = calendar.weekday(year, month, last_day)
    return last_day, ["月", "火", "水", "木", "金", "土", "日"][last_weekday]

# --- メインアプリケーション ---
st.title("シフトカレンダー自動読込プログラム")

# [1] 時程表の読み込み
try:
    time_schedule = load_time_schedule()
    st.sidebar.success("時程表の読み込み完了")
except Exception as e:
    st.sidebar.error(f"時程表読込エラー: {e}")
    st.stop()

uploaded_pdf = st.file_uploader("PDFシフト表をアップロード", type=["pdf"])

if uploaded_pdf:
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tfile.write(uploaded_pdf.read())
    tfile.close()
    
    try:
        # [2] (2) ② PDF内検索と抽出 (結果A)
        keys = list(time_schedule.keys())
        tables = camelot.read_pdf(tfile.name, flavor='stream', pages='all')
        found_key, result_A = None, None
        
        for table in tables:
            df = table.df
            for k in keys:
                for i in range(len(df)):
                    # キー検索
                    if k.replace(" ", "") in "".join(df.iloc[i].astype(str).tolist()).replace(" ", ""):
                        found_key = k
                        
                        # 堅牢な抽出ロジック (行の境界をチェック)
                        date_row = None
                        day_row = None
                        
                        # 1. keyの上下を参照を試みる
                        if i > 0 and i < len(df) - 1:
                            date_row = df.iloc[i-1]
                            day_row = df.iloc[i+1]
                        # 2. 上がダメならkeyの下2行を参照を試みる
                        elif i < len(df) - 2:
                            date_row = df.iloc[i+1]
                            day_row = df.iloc[i+2]
                            
                        if date_row is not None and day_row is not None:
                            pairs = {int(str(d)): str(day) for d, day in zip(date_row, day_row) if str(d).isdigit()}
                            if pairs:
                                result_A = (max(pairs.keys()), pairs[max(pairs.keys())])
                        break
                if found_key: break
            if found_key: break
        
        if not found_key:
            st.error("キーが見当りません。ファイルを確認して下さい。"); st.stop()
        if not result_A:
            st.error("日付データの抽出に失敗しました。ファイルを確認して下さい。"); st.stop()

        # [2] (3) ③〜⑤ 年月判定と結果Bの算出
        y, m = get_year_month_from_filename(uploaded_pdf.name)
        if not y or not m:
            y = st.number_input("年", value=datetime.now().year)
            m = st.number_input("月", value=datetime.now().month)
        
        result_B = calculate_last_date_info(y, m)
        
        # [2] (3) ⑥⑦ 整合性チェック
        if result_A == result_B:
            st.success(f"解析成功：{y}年{m}月 ({result_A[0]}日 {result_A[1]}曜日)")
        else:
            st.error("整合性エラー"); st.write(f"抽出: {result_A}, ファイル名算出: {result_B}"); st.stop()

    finally:
        if os.path.exists(tfile.name): os.remove(tfile.name)
