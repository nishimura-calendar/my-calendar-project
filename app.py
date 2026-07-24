import streamlit as st
import pandas as pd
import io
import pdfplumber
import re
import calendar
import unicodedata
import base64
import streamlit.components.v1 as components
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaIoBaseDownload
from pypdf import PdfReader
from google.auth.transport.requests import Request

# --- [1] 時程表読み込み ---
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
    
    # --- 認証切れ対策コード ---
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    # --------------------------
    
    service = build('drive', 'v3', credentials=creds)
    file_id = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"
    request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    while not downloader.next_chunk()[1]: pass
    fh.seek(0)
    df = pd.read_excel(fh, header=None, engine='openpyxl', dtype=str)
    return process_data(df)

# --- [2] PDF表示用関数 ---
# 修正箇所: base64でPDFをiframe埋め込みする形式に変更
def display_pdf(uploaded_file):
    # ファイルが存在するか確認
    if uploaded_file is None:
        st.error("PDFファイルが正しくアップロードされていません。")
        return

    try:
        # ファイルの読み込み位置を強制的に先頭に戻す
        uploaded_file.seek(0)
        pdf_data = uploaded_file.read()
        
        # データが読み込めているか確認
        if not pdf_data:
            st.error("ファイルの中身が空です。")
            return

        # base64にエンコード
        b64_pdf = base64.b64encode(pdf_data).decode('utf-8')
        
        # iframeで埋め込み表示
        pdf_display = f'<iframe src="data:application/pdf;base64,{b64_pdf}" width="100%" height="800px" type="application/pdf"></iframe>'
        st.markdown(pdf_display, unsafe_html=True)
        
    except Exception as e:
        # エラーが発生した場合、何が起きているかを表示する
        st.error(f"PDFプレビュー表示中にエラーが発生しました: {type(e).__name__} - {e}
        
st.title("シフト表解析システム")
if 'data_dict' not in st.session_state:
    st.session_state.data_dict = load_and_process_data()

uploaded_pdf = st.file_uploader("PDFシフト表をアップロード", type="pdf")

if uploaded_pdf:
    # --- Step 1: キー検索 ---
    found_key = None
    with pdfplumber.open(uploaded_pdf) as pdf:
        text = unicodedata.normalize('NFKC', pdf.pages[0].extract_text())
        for key in st.session_state.data_dict.keys():
            if str(key) in text:
                found_key = key
                break
    
    # 修正箇所: keyが見つからない場合の挙動
    if not found_key:
        st.error("勤務地(Key)がPDFから特定できませんでした。")
        display_pdf(uploaded_pdf) # ボタンなしで直接表示
        st.stop()
        
    # --- Step 2: 整合性データの抽出 ---
    with pdfplumber.open(uploaded_pdf) as pdf:
        words = pdf.pages[0].extract_words()
        date_words = [w for w in words if re.match(r'^(0?[1-9]|[12][0-9]|3[01])$', w['text'])]
        day_words = [w for w in words if w['text'] in "日月火水木金土"]
        
        last_date_obj = sorted(date_words, key=lambda x: int(x['text']))[-1]
        A_date = int(last_date_obj['text'])
        candidates = [w for w in day_words if abs(w['x0'] - last_date_obj['x0']) < 15]
        A_day = candidates[0]['text'] if candidates else "不明"

    # --- Step 3: 年月の確定 ---
    filename = uploaded_pdf.name
    year_match = re.search(r'(\d{4})', filename)
    month_match = re.search(r'(\d{1,2})月', filename)
    
    is_ready = False
    
    if year_match and month_match:
        y, m = int(year_match.group(1)), int(month_match.group(1))
        label_b = "ファイル名から算出結果"
        is_ready = True
    else:
        st.warning("年月が確認できません。年月を入力して下さい。")
        y = st.number_input("年", min_value=2000, max_value=2100, value=2026)
        m = st.number_input("月", min_value=1, max_value=12, value=3)
        label_b = "入力年月"
        if st.button("この年月で確定する"):
            is_ready = True
        else:
            st.stop()

    # --- Step 4: 整合性判定と処理 ---
    if is_ready:
        _, last_day = calendar.monthrange(y, m)
        last_day_w = ["月", "火", "水", "木", "金", "土", "日"][calendar.weekday(y, m, last_day)]
        
        # 修正箇所: 整合性判定ロジック
        is_consistent = (A_date == last_day and A_day == last_day_w)

        if is_consistent:
            # ⑥ 無言通過: ここには何も書かず、そのまま次の解析ロジックへ進ませる
            pass 
        else:
            # ⑦ 不整合時: エラー表示 + PDF表示 + 停止
            st.write(f"A：抽出結果 ＝ {A_date}日({A_day}曜日)")
            st.write(f"B：{label_b} ＝ {last_day}日({last_day_w}曜日)")
            st.error("整合性が不一致です。")
            display_pdf(uploaded_pdf) # ボタンなしで直接表示
    st.stop()
