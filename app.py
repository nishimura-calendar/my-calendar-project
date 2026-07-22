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
    # PDFをテーブル構造として読み込む
    tables = camelot.read_pdf(io.BytesIO(pdf_file.read()), pages='all', flavor='stream')
    
    results = {key: {'max_date': 0, 'last_day': None} for key in valid_keys}
    
    for table in tables:
        df = table.df
        current_key = None
        
        # 行をループして解析
        for i in range(len(df)):
            row_values = df.iloc[i].astype(str).tolist()
            row_str = " ".join(row_values)
            
            # キー（T1等）の判定
            found_key = next((k for k in valid_keys if k in row_str), None)
            if found_key:
                current_key = found_key
                continue
            
            if current_key:
                # 行の中に「31」があるか確認
                if '31' in row_values:
                    col_idx = row_values.index('31')
                    
                    # 31が見つかった場合、その周辺（同じブロック内の後続行）から曜日を探す
                    # 31日の真下や周辺に曜日（月火水木金土日）が含まれるセルを探す
                    for j in range(i + 1, min(i + 6, len(df))):
                        potential_day_row = df.iloc[j].astype(str).tolist()
                        
                        # 列インデックスが範囲内か確認し、曜日が含まれるか判定
                        if len(potential_day_row) > col_idx:
                            day_val = potential_day_row[col_idx]
                            # 曜日文字（士含む）が含まれている場合
                            if re.search(r'[月火水木金土日士]', day_val):
                                results[current_key]['max_date'] = 31
                                results[current_key]['last_day'] = day_val.replace('士', '土')
                                break
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
