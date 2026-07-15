mport streamlit as st
import pandas as pd
import io
# 【ここを追加してください】
from googleapiclient.http import MediaIoBaseDownload 
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# ... (get_service関数はそのまま) ...
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
    request = service.files().export_media(
        fileId=file_id, 
        mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    fh = io.BytesIO()
    # ここでMediaIoBaseDownloadが使われます
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    fh.seek(0)
    
    # ... (以降の処理はそのまま) ...    
df = pd.read_excel(fh, header=None, engine='openpyxl', dtype=str)
    
    location_data = {}
    location_indices = df[df.iloc[:, 0].notna()].index.tolist()
    
    for i, start_idx in enumerate(location_indices):
        key = str(df.iloc[start_idx, 0])
        end_idx = location_indices[i+1] if i+1 < len(location_indices) else len(df)
        
        # 該当範囲のデータを抽出
        row_data = df.iloc[start_idx:end_idx]
        
        # 数値（時間）が含まれる列を探す
        # A, B, C列は固定情報（勤務地、シフト、ロッカー）とみなし、D列目以降で数値を探す
        fixed_cols = [0, 1, 2] 
        extracted_rows = []
        
        for _, row in row_data.iterrows():
            new_row = row[fixed_cols].tolist()
            
            # D列以降で数値を探す
            for col_idx in range(3, len(row)):
                val = row[col_idx]
                try:
                    f_val = float(val)
                    # 小数を時刻表記（H:MM）に変換
                    h = int(f_val)
                    m = int(round((f_val - h) * 60))
                    new_row.append(f"{h}:{m:02d}")
                except (ValueError, TypeError):
                    # 数値でない場合は空欄またはそのまま
                    if pd.notna(val): new_row.append(val)
            
            extracted_rows.append(new_row)
        
        location_data[key] = pd.DataFrame(extracted_rows)
        
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
