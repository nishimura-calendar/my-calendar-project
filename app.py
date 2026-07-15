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

# 2. データを整形する関数 (打ち合わせ通りのロジック)
def process_data(df):
    location_data = {}
    # A列が値を持つ行を「勤務地行」としてインデックスを取得
    location_indices = df[df.iloc[:, 0].notna()].index.tolist()
    
    for i, start_idx in enumerate(location_indices):
        key = str(df.iloc[start_idx, 0])
        
        # 範囲確定：次の勤務地行の手前までを正確に取得
        end_idx = location_indices[i+1] if i+1 < len(location_indices) else len(df)
        schedule = df.iloc[start_idx:end_idx].copy()
        
        # --- 列方向の処理 ---
        # 勤務地行(scheduleの0行目)のD列(index 3)以降を走査
        # 「数値である限り変換し、Noneや文字が現れたらその列以降を切り取る」
        
        target_cols_limit = schedule.shape[1] # デフォルトは全列
        
        for col_idx in range(3, schedule.shape[1]):
            val = schedule.iloc[0, col_idx]
            
            # None/NaN判定と数値判定
            if pd.isna(val):
                target_cols_limit = col_idx
                break
                
            try:
                # 数値であれば時刻に変換
                f_val = float(val)
                schedule.iloc[0, col_idx] = format_time(f_val)
            except (ValueError, TypeError):
                # 数値に変換できないもの（文字列等）が現れたら切り取り
                target_cols_limit = col_idx
                break
        
        # 確定した列数で切り取り（勤務地行およびその下の行すべてに適用）
        schedule = schedule.iloc[:, :target_cols_limit]
        
        location_data[key] = schedule
        
    return location_data
# 3. 認証・読み込み処理
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

# 4. メインUI
st.title("シフト時程表ビューワー")

try:
    data_dict = load_and_process_data()
    st.subheader("勤務地を選択してください")
    
    # 以前のUI（ボタン）に戻す
    cols = st.columns(len(data_dict))
    selected_key = None
    for i, key in enumerate(data_dict.keys()):
        if cols[i].button(key):
            selected_key = key
            
    if selected_key:
        st.divider()
        st.write(f"### {selected_key} の勤務詳細")
        st.dataframe(data_dict[selected_key], hide_index=True, use_container_width=True)

except Exception as e:
    st.error(f"データの読み込み中にエラーが発生しました: {e}")
