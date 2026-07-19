import streamlit as st
import pandas as pd
import numpy as np
import io
from googleapicolient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaIoBaseDownload

def get_service():
    creds_dict = st.secrets["google_oauth_credentials"]
    creds = Credentials(**creds_dict)
    return build('drive', 'v3', credentials=creds)

@st.cache_data
def load_and_process_data_from_drive():
    service = get_service()
    file_id = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"
    
    # スプレッドシートをExcel形式としてエクスポート
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
    
    # Excelとして読み込み
    df = pd.read_excel(fh, engine='openpyxl')
    
    # --- 辞書化ロジック ---
    location_dict = {}
    current_location = None
    
    for _, row in df.iterrows():
        # A列(勤務地)の判定
        if pd.notna(row.iloc[0]) and str(row.iloc[0]).strip() != "nan":
            current_location = str(row.iloc[0]).strip()
            location_dict[current_location] = []
        
        if current_location:
            shift_info = {
                'シフトコード': row.iloc[1],
                'ロッカー': row.iloc[2],
                'time_data': {}
            }
            # D列(インデックス3)以降の数値抽出
            for i in range(3, len(row)):
                val = row.iloc[i]
                if isinstance(val, (int, float)) and not np.isnan(val):
                    shift_info['time_data'][df.columns[i]] = val
                elif isinstance(val, str):
                    break
            location_dict[current_location].append(shift_info)
    return location_dict

# メイン処理
st.title("勤務地別時程表検索")

try:
    shift_dict = load_and_process_data_from_drive()
    selected_location = st.selectbox("勤務地を選択してください", list(shift_dict.keys()))
    
    if st.button("時程を表示"):
        # 選択された勤務地の全シフトデータを表示
        df_display = pd.DataFrame(shift_dict[selected_location])
        st.dataframe(df_display)
except Exception as e:
    st.error(f"データの取得・処理中にエラーが発生しました: {e}")
