import streamlit as st
import pandas as pd
import io
import tempfile
import os
import re
import calendar
import fitz  # PyMuPDF
import pdfplumber  # camelotの代わりに追加
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# --- [1] 各種関数 ---
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

def extract_date_day_pairs(df, key):
    for i in range(len(df)):
        row_values = df.iloc[i].astype(str).tolist()
        if key in row_values:
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

def display_pdf_as_image(file_path):
    try:
        doc = fitz.open(file_path)
        page = doc.load_page(0)
        pix = page.get_pixmap()
        img_data = pix.tobytes("png")
        st.warning("ファイル内容を確認してください：")
        st.image(img_data, use_container_width=True)
        doc.close()
    except Exception:
        pass

def get_year_month_from_filename(filename):
    year_match = re.search(r'(\d{4})', filename)
    month_match = re.search(r'(\d{1,2})月', filename)
    return (int(year_match.group(1)) if year_match else None, 
            int(month_match.group(1)) if month_match else None)

def calculate_last_date_info(year, month):
    _, last_day = calendar.monthrange(year, month)
    last_weekday = calendar.weekday(year, month, last_day)
    return last_day, ["月", "火", "水", "木", "金", "土", "日"][last_weekday]

# --- 解析用ラッパークラス ---
class TableWrapper:
    def __init__(self, df):
        self.df = df

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
    
    should_delete = True
    
    try:
        # 1. 解析処理（pdfplumberへ移行）
        tables = []
        with pdfplumber.open(tfile.name) as pdf:
            for page in pdf.pages:
                extracted_tables = page.extract_tables()
                for table_data in extracted_tables:
                    df = pd.DataFrame(table_data)
                    tables.append(TableWrapper(df))
        
        if not tables:
            st.error("エラー：このファイルから表を検出できませんでした。")
            should_delete = False
            display_pdf_as_image(tfile.name)
            st.stop()

        found_key, result_A = None, None
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
            st.error("勤務地が見当りません。")
            should_delete = False
            display_pdf_as_image(tfile.name)
            st.stop()

        # 2. 年月取得と入力フォーム
        file_y, file_m = get_year_month_from_filename(uploaded_pdf.name)
        
        if not file_y or not file_m:
            st.write("年月を入力して下さい。")
            y = st.number_input("年", value=datetime.now().year)
            m = st.number_input("月", value=datetime.now().month)
            st.stop()
        else:
            y, m = file_y, file_m
            
        result_B = calculate_last_date_info(y, m)
        
        # 3. 整合性チェック
        if result_A == result_B:
            st.success(f"解析成功：{y}年{m}月 ({result_A[0]}日 {result_A[1]}曜日)")
        else:
            st.error("❌ エラー：データとファイル名の年月が一致しません。")
            should_delete = False
            display_pdf_as_image(tfile.name)
            st.stop()

    finally:
        if should_delete and os.path.exists(tfile.name):
            os.remove(tfile.name)
