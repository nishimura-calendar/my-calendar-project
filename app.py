import streamlit as st
import pandas as pd
import io
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# 1. 認証サービス取得（エラー詳細表示用）
def get_service():
    try:
        creds_dict = st.secrets["google_oauth_credentials"]
        creds = Credentials(
            token=creds_dict["token"],
            refresh_token=creds_dict["refresh_token"],
            token_uri=creds_dict["token_uri"],
            client_id=creds_dict["client_id"],
            client_secret=creds_dict["client_secret"]
        )
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"認証情報のエラー: {e}")
        return None
# 時刻変換関数
def format_time(val):
    try:
        f_val = float(val)
        h = int(f_val)
        m = int(round((f_val - h) * 60))
        return f"{h}:{m:02d}"
    except (ValueError, TypeError):
        return val

# 読み込んだdfを整形する関数
def process_data(df):
    location_data = {}
    # A列が空でない行（勤務地行）を取得
    location_indices = df[df.iloc[:, 0].notna()].index.tolist()
    
    for i, start_idx in enumerate(location_indices):
        key = str(df.iloc[start_idx, 0])
        end_idx = location_indices[i+1] if i+1 < len(location_indices) else len(df)
        
        # 範囲を抽出
        schedule = df.iloc[start_idx:end_idx].copy()
        
        # 数値列（D列以降＝インデックス3以降）を時刻形式に変換
        for col in schedule.columns:
            if col >= 3: 
                schedule[col] = schedule[col].apply(format_time)
        
        location_data[key] = schedule
    return location_data

# メイン表示
st.title("シフト時程表ビューワー")
df = load_time_schedule() # 先ほどの読み込み関数

if df is not None:
    data_dict = process_data(df)
    
    st.subheader("勤務地を選択してください")
    cols = st.columns(len(data_dict))
    
    for i, key in enumerate(data_dict.keys()):
        if cols[i].button(key):
            st.session_state['selected_key'] = key
            
    if 'selected_key' in st.session_state:
        target = st.session_state['selected_key']
        st.write(f"### {target} の時程表")
        st.dataframe(data_dict[target], hide_index=True)
