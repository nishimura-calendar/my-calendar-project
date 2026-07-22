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
    # PDF読み込み
    tables = camelot.read_pdf(io.BytesIO(pdf_file.read()), pages='all', flavor='stream')
    full_df = pd.concat([t.df for t in tables], ignore_index=True)
    
    results = {key: {'max_date': 0, 'last_day': None} for key in valid_keys}
    date_pattern = re.compile(r'\b([12]?\d|3[01])\b')
    weekday_pattern = re.compile(r'[月火水木金土日]')
    current_key = None
    
    # 行番号付きで走査
    for idx in range(len(full_df)):
        row = full_df.iloc[idx]
        row_str = " ".join([str(v) for v in row]).replace('\n', ' ').strip()
        
        # (1)(2) Key検知と第1関門
        found_key = next((k for k in valid_keys if k in row_str), None)
        if found_key:
            current_key = found_key
            continue
            
        # (3) Keyブロック内の最終日付・曜日抽出
        if current_key:
            dates = [int(d) for d in date_pattern.findall(row_str)]
            
            if dates:
                max_d_in_row = max(dates)
                
                # 【修正箇所】次の行（idx + 1）から曜日を探す
                day_in_row = None
                if idx + 1 < len(full_df):
                    next_row = full_df.iloc[idx + 1]
                    next_row_str = " ".join([str(v) for v in next_row]).replace('\n', ' ').strip()
                    weekdays = weekday_pattern.findall(next_row_str)
                    if weekdays:
                        day_in_row = weekdays[0] # 見つかった曜日を採用
                
                # 最終日付比較：大きい方を保持
                if max_d_in_row > results[current_key]['max_date']:
                    results[current_key]['max_date'] = max_d_in_row
                    results[current_key]['last_day'] = day_in_row
                    
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
