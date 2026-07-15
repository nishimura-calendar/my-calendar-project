import streamlit as st
import pandas as pd
import io
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# 1. 認証情報の取得（既存のまま）
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

# 3. データを整形する関数（修正部分）
def process_data(df):
    location_data = {}
    # A列が空でない行（勤務地行）のインデックスを取得
    location_indices = df[df.iloc[:, 0].notna()].index.tolist()
    
    for start_idx in location_indices:
        key = str(df.iloc[start_idx, 0])
        
        # 次の勤務地行を探して範囲を確定する
        end_idx = df.index[-1] + 1
        for next_idx in location_indices:
            if next_idx > start_idx:
                end_idx = next_idx
                break
        
        # 該当範囲のデータを抽出
        schedule = df.iloc[start_idx:end_idx].copy()
        
        # D列(index 3)以降を走査し、数値から文字に変わるまで変換
        for row_idx in range(len(schedule)):
            for col_idx in range(3, schedule.shape[1]):
                val = schedule.iloc[row_idx, col_idx]
                
                # 数値変換を試みる
                try:
                    float(val)
                    schedule.iloc[row_idx, col_idx] = format_time(val)
                except (ValueError, TypeError):
                    # 文字が現れた時点で、この行の変換を停止
                    break
        
        location_data[key] = schedule
            
    return location_data

# 4. メイン処理（既存のまま）
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
    
    # 勤務地（key）を選択
    selected_key = st.selectbox("勤務地を選択", list(data_dict.keys()))
            
    if selected_key:
        st.divider()
        st.write(f"### {selected_key} の勤務詳細")
        st.dataframe(data_dict[selected_key], hide_index=True, use_container_width=True)

except Exception as e:
    st.error(f"データの読み込み中にエラーが発生しました: {e}")
