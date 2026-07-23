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

# --- [1] 時程表読込ロジック ---
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

# --- [2] 抽出ロジック (app(38).pyのロジックを関数化) ---
def extract_date_day_pairs(df, key):
    # テーブル全体を走査して key を含む行を探す
    for i in range(len(df)):
        row_values = df.iloc[i].astype(str).tolist()
        if key in row_values:
            # key行の次の行を「曜日行」、その上の行を「日付行」と仮定
            date_row = df.iloc[i-1].values if i > 0 else None
            day_row = df.iloc[i+1].values if i < len(df)-1 else None
            
            if date_row is not None and day_row is not None:
                pairs = {}
                for col in range(len(date_row)):
                    d = str(date_row[col]).strip()
                    day = str(day_row[col]).strip()
                    if d.isdigit() and day in "日月火水木金土":
                        pairs[int(d)] = day
                
                if pairs:
                    last_date = max(pairs.keys())
                    return last_date, pairs[last_date], None
    return None, None, f"{key} 行付近から日付と曜日のペアを抽出できませんでした。"

# --- [3] 共通関数 (年月取得・算出) ---
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

try:
    time_schedule = load_time_schedule()
except Exception as e:
    st.error(f"時程表読込エラー: {e}"); st.stop()

uploaded_pdf = st.file_uploader("PDFシフト表をアップロード", type=["pdf"])

if uploaded_pdf:
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tfile.write(uploaded_pdf.read())
    tfile.close()
    
    try:
        # PDF解析
        tables = camelot.read_pdf(tfile.name, flavor='stream', pages='all')
        found_key, result_A = None, None
        
        # [2] 抽出ロジックの適用[cite: 5]
        keys = list(time_schedule.keys())
        for table in tables:
            df = table.df
            for k in keys:
                last_date, last_day, error = extract_date_day_pairs(df, k)
                if not error:
                    result_A = (last_date, last_day)
                    found_key = k
                    break
            if found_key: break
        
        if not found_key:
            st.error("指定された key が PDF 内に見つかりませんでした。"); st.stop()

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
