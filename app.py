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
    # (1) 一時ファイルとして保存して読み込み
    temp_path = "temp_shift.pdf"
    with open(temp_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    tables = camelot.read_pdf(temp_path, flavor='lattice', pages='all')
    df = tables[0].df
    
    # 解析後は削除
    if os.path.exists(temp_path):
        os.remove(temp_path)

    # (2) 第1関門：Key検索
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
        st.error("指定された勤務地が見当たりません。シフト表ではないようです。")
        st.dataframe(df)
        st.stop()

    # (3) 第2関門：年月と日付の整合性
    # ② Key行より上の行から最大日付(A)を抽出
    max_date_a = 0
    target_area = df.iloc[:key_row_idx, :]
    for col in range(target_area.shape[1]):
        for val in target_area.iloc[:, col]:
            try:
                n = float(val)
                if 1 <= n <= 31 and n > max_date_a:
                    max_date_a = int(n)
            except (ValueError, TypeError):
                continue

    # ③ ファイル名から年月を取得
    file_name = uploaded_file.name
    date_match = re.search(r'(\d{4}).*?(\d{1,2})', file_name)
    
    if not date_match:
        year = st.number_input("年を入力してください", 2026)
        month = st.number_input("月を入力してください", 1)
    else:
        year, month = int(date_match.group(1)), int(date_match.group(2))

    # ⑤ B：取得した年月から最終日付を取得
    _, last_day_b = calendar.monthrange(year, month)
    
    # ⑥⑦⑧ 判定
    if max_date_a == last_day_b:
        st.success("第2関門通過")
        return found_key, df, key_row_idx
    else:
        st.error(f"日付不一致: PDF({max_date_a}日) != {year}年{month}月({last_day_b}日)")
        st.dataframe(df)
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
