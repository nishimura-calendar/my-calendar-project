import streamlit as st
import pandas as pd
import io
import tempfile
import os
import re
import calendar
import fitz  # PyMuPDF
import pdfplumber  # camelotの代わりに使用
from datetime import datetime
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

# ValueErrorを回避する堅牢な抽出関数
def extract_date_day_pairs(df, key):
    # 1. データの安全確認: 空でないかチェックし、NaNを空文字に置換
    if df is None or df.empty:
        return None, None, "テーブルデータが空です。"
    
    # 処理前にNaNを空文字に変換しておくことで、str変換時のエラーを完全に防ぐ
    df = df.fillna('')

    # 2. Key行の探索
    key_row_idx = -1
    for i in range(len(df)):
        # iloc[i]がSeriesとして正しく取得できるか確認
        try:
            row_values = df.iloc[i].values
            # リスト内包表記で安全に文字列化
            row_str = " ".join([str(v) for v in row_values])
            if key in row_str:
                key_row_idx = i
                break
        except Exception:
            continue # 読み取れない行はスキップ
            
    if key_row_idx == -1:
        return None, None, f"キー '{key}' が見つかりませんでした。"

    # 3. 日付行の探索（Keyの周辺で行う）
    target_date_idx = -1
    for i in [key_row_idx - 1, key_row_idx, key_row_idx + 1]:
        if 0 <= i < len(df):
            row_vals = df.iloc[i].values
            # 数値の並び（1〜31の数字）が5つ以上ある行を探す
            digit_count = sum(1 for v in row_vals if re.search(r'^\d+$', str(v).strip()))
            if digit_count >= 5:
                target_date_idx = i
                break
    
    if target_date_idx == -1:
        return None, None, f"キー '{key}' 付近に日付データが見つかりませんでした。"

    # 4. 日付・曜日抽出
    date_row = df.iloc[target_date_idx].values
    day_row = df.iloc[target_date_idx + 1].values if target_date_idx + 1 < len(df) else None
    
    pairs = {}
    for col in range(len(date_row)):
        d_val = str(date_row[col]).strip()
        day_val = str(day_row[col]).strip() if day_row is not None else ""
        
        # 数字のみ抽出
        d_digit = re.sub(r'\D', '', d_val)
        
        # 曜日抽出（漢字1文字）
        day = ""
        for char in day_val:
            if char in "日月火水木金土":
                day = char
                break
        
        if d_digit.isdigit() and day != "":
            pairs[int(d_digit)] = day
            
    if pairs:
        last_date = max(pairs.keys())
        return last_date, pairs[last_date], None
        
    return None, None, "日付と曜日のペアが抽出できませんでした。"
    
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
        # 1. 解析処理（pdfplumberへ完全移行）
        tables = []
        try:
            with pdfplumber.open(tfile.name) as pdf:
                for page in pdf.pages:
                    for table_data in page.extract_tables():
                        df = pd.DataFrame(table_data)
                        tables.append(TableWrapper(df))
            
            if not tables:
                raise Exception("表を検出できませんでした。")
        except Exception as e:
            st.error(f"解析エラー: {e}")
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
            st.error(f"❌ エラー：データとファイル名の年月が一致しません。\n\n"
                     f"抽出結果: {result_A[0]}日 {result_A[1]}曜日\n"
                     f"想定結果: {result_B[0]}日 {result_B[1]}曜日")
            should_delete = False
            display_pdf_as_image(tfile.name)
            st.stop()

    finally:
        if should_delete and os.path.exists(tfile.name):
            os.remove(tfile.name)
