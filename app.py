import streamlit as st
import pandas as pd
import io
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# 認証情報の取得（Secretsを使用）
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

# 勤務地ごとの時間表記への変換関数
def format_time(val):
    try:
        f_val = float(val)
        h = int(f_val)
        m = int(round((f_val - h) * 60))
        return f"{h}:{m:02d}"
    except (ValueError, TypeError):
        return val

@st.cache_data
def load_time_schedule():
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
    
    # データを読み込み
    df = pd.read_excel(fh, header=None, engine='openpyxl')
    
    location_data = {}
    # A列が空でない行を「勤務地行(キー)」として抽出
    location_indices = df[df.iloc[:, 0].notna()].index.tolist()
    
    for i, start_idx in enumerate(location_indices):
        key = str(df.iloc[start_idx, 0])
        end_idx = location_indices[i+1] if i+1 < len(location_indices) else len(df)
        
        # この範囲を一つの時程表とする
        schedule_df = df.iloc[start_idx:end_idx].copy()
        
        # 時間列（数値列）の変換
        # 列ごとに数値変換を試み、成功すれば時刻形式にする
        for col in schedule_df.columns:
            # 勤務地(0), シフト(1), ロッカー(2)列はスキップ
            if col > 2:
                schedule_df[col] = schedule_df[col].apply(format_time)
        
        location_data[key] = schedule_df
        
    return location_data

# --- UI部分 ---
st.title("シフト時程表ビューワー")

try:
    data = load_time_schedule()
    
    st.subheader("勤務地を選択してください")
    
    # 勤務地ボタンを横に並べる
    cols = st.columns(len(data))
    for i, key in enumerate(data.keys()):
        if cols[i].button(key):
            st.session_state['selected_key'] = key
            
    # 選択された時程表の表示
    if 'selected_key' in st.session_state:
        target_key = st.session_state['selected_key']
        st.write(f"### {target_key} の時程表")
        st.dataframe(data[target_key], hide_index=True)

except Exception as e:
    st.error(f"データの読み込み中にエラーが発生しました: {e}")
