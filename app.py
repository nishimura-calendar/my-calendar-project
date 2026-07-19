import streamlit as st
import pandas as pd
import io
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# 1. 小数から時刻表記(H:MM)への変換関数
def format_time(val):
    try:
        f_val = float(val)
        h = int(f_val)
        m = int(round((f_val - h) * 60))
        return f"{h}:{m:02d}"
    except (ValueError, TypeError):
        return val

# 2. データを整形する関数
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

# 3. 認証・読み込み・辞書登録処理
@st.cache_data(ttl=600)
def get_latest_schedule_to_dict():
    creds_dict = st.secrets["google_oauth_credentials"]
    creds = Credentials(
        token=creds_dict["token"],
        refresh_token=creds_dict["refresh_token"],
        token_uri=creds_dict["token_uri"],
        client_id=creds_dict["client_id"],
        client_secret=creds_dict["client_secret"]
    )
    service = build('drive', 'v3', credentials=creds)
    
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

# --- メイン処理 ---
st.title("勤務地スケジュール選択")

# 辞書の取得
data_dict = get_latest_schedule_to_dict()

# 勤務地（key）ボタンを表示
st.subheader("勤務地を選択してください")
cols = st.columns(len(data_dict))

# 選択状態を保持する変数をセッションステートに格納
if 'selected_key' not in st.session_state:
    st.session_state.selected_key = None

for i, key in enumerate(data_dict.keys()):
    if cols[i].button(key):
        st.session_state.selected_key = key

# ボタンが押されたらスケジュールを表示
if st.session_state.selected_key:
    st.divider()
    st.write(f"### {st.session_state.selected_key} の勤務詳細")
    st.dataframe(data_dict[st.session_state.selected_key], hide_index=True, use_container_width=True)
