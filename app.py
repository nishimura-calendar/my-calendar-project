import streamlit as st
import pandas as pd
import io
import pdfplumber
import re
import calendar
import unicodedata
import base64
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaIoBaseDownload
from pypdf import PdfReader

# --- [1] 時程表読み込み (添付ロジック) ---
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
        key = str(df.iloc[start_idx, 0])
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
def load_and_process_data():
    creds_dict = st.secrets["google_oauth_credentials"]
    creds = Credentials(**creds_dict)
    service = build('drive', 'v3', credentials=creds)
    file_id = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"
    request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    while not downloader.next_chunk()[1]: pass
    fh.seek(0)
    df = pd.read_excel(fh, header=None, engine='openpyxl', dtype=str)
    return process_data(df)

# --- [2] PDF解析・整合性チェック ---
def display_pdf(uploaded_file):
    base64_pdf = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')
    st.markdown(f'<embed src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800px" type="application/pdf">', unsafe_allow_html=True)

st.title("シフト表解析システム")
if 'data_dict' not in st.session_state:
    st.session_state.data_dict = load_and_process_data()

uploaded_pdf = st.file_uploader("PDFシフト表をアップロード", type="pdf")

if uploaded_pdf:
    # (2) ① キー検索
    found_key = None
    with pdfplumber.open(uploaded_pdf) as pdf:
        text = unicodedata.normalize('NFKC', pdf.pages[0].extract_text())
        for key in st.session_state.data_dict.keys():
            if str(key) in text:
                found_key = key
                break
    
    if not found_key:
        st.error("勤務地(Key)が確認できません。")
        display_pdf(uploaded_pdf)
        st.stop()

    # (3) ②〜⑦ 整合性チェック (曜日の抽出ロジック更新)
    with pdfplumber.open(uploaded_pdf) as pdf:
        page = pdf.pages[0]
        words = page.extract_words()
        
        # 日付と曜日を抽出
        date_words = [w for w in words if re.match(r'^(0?[1-9]|[12][0-9]|3[01])$', w['text'])]
        day_words = [w for w in words if w['text'] in "日月火水木金土"]
        
        # 最終日を探す
        last_date_obj = sorted(date_words, key=lambda x: int(x['text']))[-1]
        A_date = int(last_date_obj['text'])
        
        # 日付に近い曜日を探す（X座標の差が小さいもの）
        candidates = [w for w in day_words if abs(w['x0'] - last_date_obj['x0']) < 15]
        A_day = candidates[0]['text'] if candidates else "不明"

    # ファイル名から年月算出
    filename = uploaded_pdf.name
    y_m = re.search(r'(20\d{2})[^\d]*(\d{1,2})', filename)
    
    if y_m:
        y, m = int(y_m.group(1)), int(y_m.group(2))
        label_b = "ファイル名から算出結果"
    else:
        st.error("年月が不明です。入力してください。")
        y = st.number_input("年", value=2026)
        m = st.number_input("月", value=1)
        label_b = "入力年月から算出結果"
        if not st.button("確定"): st.stop()

    _, last_day = calendar.monthrange(y, m)
    last_day_w = ["月", "火", "水", "木", "金", "土", "日"][calendar.weekday(y, m, last_day)]
    
    st.write(f"A：抽出結果 ＝ {A_date}日({A_day}曜日)")
    
    if A_date == last_day and A_day == last_day_w:
        st.success("整合性確認OK")
        st.stop()
    else:
        st.write(f"B：{label_b} ＝ {last_day}日({last_day_w}曜日)")
        st.error("ファイルを確認して下さい。")
        display_pdf(uploaded_pdf)
        st.stop()
