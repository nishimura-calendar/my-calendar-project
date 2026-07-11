import streamlit as st
import pandas as pd
import io
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# 1. 認証情報の取得
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

# 2. 小数から時刻表記(H:MM)への変換関数
def format_time(val):
    try:
        f_val = float(val)
        h = int(f_val)
        m = int(round((f_val - h) * 60))
        return f"{h}:{m:02d}"
    except (ValueError, TypeError):
        return val

# 3. データを整形する関数（勤務地行のみ変換）
def process_data(df):
    location_data = {}
    location_indices = df[df.iloc[:, 0].notna()].index.tolist()
    
    for i, start_idx in enumerate(location_indices):
        key = str(df.iloc[start_idx, 0])
        end_idx = location_indices[i+1] if i+1 < len(location_indices) else len(df)
        
        schedule = df.iloc[start_idx:end_idx].copy()
        
        # 行ごとに処理（勤務地行のみ変換）
        for row_idx in range(len(schedule)):
            if row_idx == 0:  # 勤務地行（ヘッダー行）
                for col_idx in range(3, len(schedule.columns)):
                    schedule.iloc[row_idx, col_idx] = format_time(schedule.iloc[row_idx, col_idx])
            # 他の行（シフト等）は何もしない
        
        location_data[key] = schedule
    return location_data

# 4. メイン処理
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

st.title("シフト時程表ビューワー")

try:
    data_dict = load_and_process_data()
    
    st.subheader("勤務地を選択してください")
    
    cols = st.columns(len(data_dict))
    for i, key in enumerate(data_dict.keys()):
        if cols[i].button(key):
            st.session_state['selected_key'] = key
            
    if 'selected_key' in st.session_state:
        target_key = st.session_state['selected_key']
        st.divider()
        st.write(f"### {target_key} の時程表")
        st.dataframe(data_dict[target_key], hide_index=True)

except Exception as e:
    st.error(f"データの読み込み中にエラーが発生しました: {e}")
