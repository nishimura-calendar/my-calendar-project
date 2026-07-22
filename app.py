import streamlit as st
import pandas as pd
import camelot
import re
import io
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# --- [1] 時程表の辞書登録ロジック (変更不可) ---
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

# --- [2] PDF解析ロジック ---
def parse_shift_pdf(pdf_file, valid_keys):
    tables = camelot.read_pdf(io.BytesIO(pdf_file.read()), pages='all', flavor='stream')
    
    # 全テーブルの全セルを「1つの平坦なリスト」に変換して、文字の流れを作る
    all_cells = []
    for table in tables:
        # DataFrameをフラットなリストにする
        all_cells.extend(table.df.values.flatten().tolist())
    
    results = {key: {'max_date': 0, 'last_day': None} for key in valid_keys}
    current_key = None
    
    # 曜日パターン
    weekday_pattern = re.compile(r'[月火水木金土日士]')
    
    for i, cell_val in enumerate(all_cells):
        cell_str = str(cell_val)
        
        # 1. キーの更新（T1などの判定）
        found_key = next((k for k in valid_keys if k in cell_str), None)
        if found_key:
            current_key = found_key
            continue
            
        if current_key:
            # 2. 「31」という文字が含まれているか確認
            if '31' in cell_str:
                results[current_key]['max_date'] = 31
                
                # 「31」が含まれる文字列の中で、さらに改行やその後の文字に曜日がないか探索
                # 31より「後ろ」の文字列を連結して曜日を探す（最大5セル先までチェック）
                search_text = cell_str
                for j in range(1, 4):
                    if i + j < len(all_cells):
                        search_text += " " + str(all_cells[i + j])
                
                # 31より「後ろ」にある最初の曜日文字を取得
                # 31の直前にある文字は無視するようパターンを工夫
                match = weekday_pattern.search(search_text.split('31')[-1])
                if match:
                    results[current_key]['last_day'] = match.group().replace('士', '土')
                    
    return results  
    
# --- [3] Google連携・メインUI ---
def get_service():
    creds_dict = st.secrets["google_oauth_credentials"]
    creds = Credentials(
        token=creds_dict["token"],
        refresh_token=creds_dict["refresh_token"],
        token_uri=creds_dict["token_uri"],
        client_id=creds_dict["client_id"],
        client_secret=creds_dict["client_secret"]
    )
    return build('drive', 'v3', credentials=creds)

@st.cache_data(ttl=600)
def load_and_process_data():
    service = get_service()
    file_id = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"
    # 【修正箇所】 file_id -> fileId に変更
    request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    df = pd.read_excel(fh, header=None, engine='openpyxl', dtype=str)
    return process_data(df)

st.title("シフト解析システム")

try:
    data_dict = load_and_process_data()
    valid_keys = list(data_dict.keys())
    
    uploaded_pdf = st.file_uploader("シフト表PDFをアップロード", type="pdf")
    if uploaded_pdf:
        with st.spinner('解析中...'):
            results = parse_shift_pdf(uploaded_pdf, valid_keys)
            st.write("### 解析結果")
            for key, info in results.items():
                if info['max_date'] > 0:
                    st.success(f"【{key}】: 最終日付 {info['max_date']}日 ({info['last_day']}曜日)")
                else:
                    st.info(f"【{key}】: データなし")
except Exception as e:
    st.error(f"システムエラー: {e}")
