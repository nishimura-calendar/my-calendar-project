import streamlit as st
import pandas as pd
import camelot
import re
import calendar
import io
import os
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaIoBaseDownload

# --- [1]．時程表読込用の関数群 ---
def get_service():
    creds_dict = st.secrets["google_oauth_credentials"]
    creds = Credentials(**creds_dict)
    return build('drive', 'v3', credentials=creds)

@st.cache_data(ttl=600)
def load_and_process_data():
    service = get_service()
    file_id = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"
    request = service.files().export_media(
        fileId=file_id, 
        mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    df = pd.read_excel(fh, header=None, engine='openpyxl', dtype=str)
    return process_data(df)

def process_data(df):
    location_data = {}
    location_indices = df[df.iloc[:, 0].notna()].index.tolist()
    for i, start_idx in enumerate(location_indices):
        key = str(df.iloc[start_idx, 0]).strip()
        end_idx = location_indices[i+1] if i+1 < len(location_indices) else df.index[-1] + 1
        location_data[key] = df.iloc[start_idx:end_idx].copy()
    return location_data

# --- [2]．pdfシフト表ファイル読込 ---
def process_pdf_shift(uploaded_file, data_dict):
    temp_path = "temp_shift.pdf"
    with open(temp_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    tables = camelot.read_pdf(temp_path, flavor='lattice', pages='all')
    df = tables[0].df
    
    if os.path.exists(temp_path):
        os.remove(temp_path)

    # Key検索
    found_key = None
    key_row_idx = -1
    for idx, row in df.iterrows():
        cell_val = str(row[0])
        clean_cell = re.sub(r'[\s ]', '', cell_val)
        for key in data_dict.keys():
            if re.sub(r'[\s ]', '', key) in clean_cell:
                found_key = key
                key_row_idx = idx
                break
        if found_key: break

    if not found_key:
        st.error("指定された勤務地が見当たりません。")
        st.stop()

    # --- 修正箇所：年月取得と最終日付判定 ---
    file_name = uploaded_file.name
    # 4桁の年と、それに続く1-2桁の月を抽出（例：2026年1月）
    date_match = re.search(r'(\d{4}).*?(\d{1,2})', file_name)
    
    if date_match:
        year, month = int(date_match.group(1)), int(date_match.group(2))
        st.info(f"ファイル名から {year}年{month}月 を認識しました。")
    else:
        st.warning("ファイル名から年月が認識できませんでした。")
        year = st.number_input("年を入力してください", 2026)
        month = st.number_input("月を入力してください", 1)

    # 最終日付の抽出（全データ対象に正規表現を使用）
    max_date_a = 0
    for col in range(df.shape[1]):
        for val in df.iloc[:, col]:
            matches = re.findall(r'\b([1-9]|[12][0-9]|3[01])\b', str(val))
            for m in matches:
                if int(m) > max_date_a:
                    max_date_a = int(m)

    _, last_day_b = calendar.monthrange(year, month)
    
    if max_date_a == last_day_b:
        st.success(f"第2関門通過: {year}年{month}月は {max_date_a}日まで確認できました。")
        return found_key, df, key_row_idx
    else:
        st.error(f"日付不一致: PDF内の最大日付({max_date_a}日) != {year}年{month}月({last_day_b}日)")
        st.stop()

# --- メイン実行部 ---
st.title("シフトカレンダー取込")
try:
    data_dict = load_and_process_data()
    uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")
    if uploaded_file:
        found_key, df_pdf, key_row = process_pdf_shift(uploaded_file, data_dict)
        # 次のステップの実装へ続く...
except Exception as e:
    st.error(f"エラーが発生しました: {e}")
