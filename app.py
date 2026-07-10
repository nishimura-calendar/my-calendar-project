import streamlit as st
import pandas as pd
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import io

# Secretsから認証情報を取得
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

# スプレッドシートを読み込み、辞書形式に変換する関数
@st.cache_data
def load_time_schedule():
    service = get_service()
    file_id = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"
    
    # Drive APIでスプレッドシートをエクスポート
    request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    downloader.next_chunk()
    fh.seek(0)
    
    df = pd.read_excel(fh, header=None, engine='openpyxl')
    
    # 勤務地(key)ごとにデータを抽出するロジック
    location_data = {}
    # 簡易的なロジック：A列に値がある行を勤務地の開始とみなす
    location_indices = df[df.iloc[:, 0].notna()].index.tolist()
    
    for i, start_idx in enumerate(location_indices):
        key = str(df.iloc[start_idx, 0])
        end_idx = location_indices[i+1] if i+1 < len(location_indices) else len(df)
        schedule = df.iloc[start_idx:end_idx]
        location_data[key] = schedule
        
    return location_data

# メイン処理
st.title("シフト時程表ビューワー")

try:
    data = load_time_schedule()
    
    st.subheader("勤務地を選択してください")
    
    # カラムを使用してボタンを配置（横並びにする工夫）
    cols = st.columns(len(data))
    
    for i, (key, schedule) in enumerate(data.items()):
        if cols[i].button(key):
            st.session_state['selected_key'] = key
            
    # ボタンが押された後の表示
    if 'selected_key' in st.session_state:
        st.divider()
        st.write(f"### {st.session_state['selected_key']} の時程表")
        st.dataframe(data[st.session_state['selected_key']])

except Exception as e:
    st.error(f"データの読み込み中にエラーが発生しました: {e}")
