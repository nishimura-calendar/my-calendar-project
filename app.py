import streamlit as st
import pandas as pd
import io
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# 1. 認証サービス取得
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

# 2. 数値を時刻表記(H:MM)に変換する関数
def format_time(val):
    try:
        f_val = float(val)
        h = int(f_val)
        m = int(round((f_val - h) * 60))
        return f"{h}:{m:02d}"
    except (ValueError, TypeError):
        return val

# 3. 時程表を読み込み、辞書形式に変換する関数
@st.cache_data(ttl=600)
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
    
    # 全データを文字列として読み込む
    df = pd.read_excel(fh, header=None, engine='openpyxl', dtype=str)
    
    location_data = {}
    # A列が空でない行を「勤務地行」として抽出
    location_indices = df[df.iloc[:, 0].notna()].index.tolist()
    
    for i, start_idx in enumerate(location_indices):
        key = str(df.iloc[start_idx, 0])
        end_idx = location_indices[i+1] if i+1 < len(location_indices) else len(df)
        
        # 該当範囲のデータを抽出
        schedule = df.iloc[start_idx:end_idx].copy()
        
        # D列以降（インデックス3以降）が時間行の対象
        for col in schedule.columns:
            if col >= 3:
                schedule[col] = schedule[col].apply(format_time)
        
        location_data[key] = schedule
        
    return location_data

# 4. メイン画面の構築
st.title("シフト時程表ビューワー")

try:
    data_dict = load_time_schedule()
    
    st.subheader("勤務地を選択してください")
    
    # ボタンを横並びに配置
    cols = st.columns(len(data_dict))
    for i, key in enumerate(data_dict.keys()):
        if cols[i].button(key):
            st.session_state['selected_key'] = key
            
    # ボタン押下後の表示
    if 'selected_key' in st.session_state:
        target_key = st.session_state['selected_key']
        st.divider()
        st.write(f"### {target_key} の時程表")
        # インデックスを隠してデータフレームを表示
        st.dataframe(data_dict[target_key], hide_index=True)

except Exception as e:
    st.error(f"データの読み込み中にエラーが発生しました: {e}")
