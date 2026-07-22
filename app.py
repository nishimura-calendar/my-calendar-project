import streamlit as st
import pandas as pd
import camelot
import io
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaIoBaseDownload

# --- [1] 関数定義 ---

def process_data(df):
    location_data = {}
    # キー（T1等）を取得するロジックは維持
    location_indices = df[df.iloc[:, 0].notna()].index.tolist()
    for i, start_idx in enumerate(location_indices):
        key = str(df.iloc[start_idx, 0])
        location_data[key] = True 
    return location_data

def load_and_process_data():
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
    request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    df = pd.read_excel(fh, header=None, engine='openpyxl', dtype=str)
    return process_data(df)

def parse_shift_pdf(pdf_file, valid_keys):
    tables = camelot.read_pdf(io.BytesIO(pdf_file.read()), pages='all', flavor='stream')
    results = {key: {'max_date': 0, 'day_of_week': "不明"} for key in valid_keys}
    processed_keys = set()

    for table in tables:
        df = table.df
        current_key = None
        for i in range(len(df)):
            row_values = df.iloc[i].astype(str).tolist()
            # 行の先頭がキーと一致するか確認
            if row_values[0] in valid_keys:
                current_key = row_values[0]
                continue
            
            # T1等のキーが見つかっており、まだデータ未抽出の場合
            if current_key and current_key not in processed_keys:
                # 数値変換を試みて、数値が含まれるか判定
                nums = []
                for val in row_values:
                    try:
                        nums.append(int(val))
                    except:
                        nums.append(-1)
                
                # 数値が5つ以上あれば日付行とみなす
                if len([n for n in nums if n > 0]) >= 5:
                    max_d = max(nums)
                    col_idx = nums.index(max_d)
                    
                    # 曜日行（直下の行）から取得
                    if i + 1 < len(df):
                        day_row = df.iloc[i+1].astype(str).tolist()
                        results[current_key]['max_date'] = max_d
                        results[current_key]['day_of_week'] = day_row[col_idx].replace('|', '').strip()
                    
                    processed_keys.add(current_key)
    return results

# --- [2] メインUI ---
st.title("シフト解析システム")

if 'valid_keys' not in st.session_state:
    try:
        data_dict = load_and_process_data()
        st.session_state['valid_keys'] = list(data_dict.keys())
    except Exception as e:
        st.error(f"データ読み込み失敗: {e}")
        st.session_state['valid_keys'] = []

uploaded_pdf = st.file_uploader("シフト表PDFをアップロード", type="pdf")

if uploaded_pdf:
    valid_keys = st.session_state.get('valid_keys', [])
    if not valid_keys:
        st.error("解析用キーが見つかりません。")
    else:
        with st.spinner('解析中...'):
            try:
                results = parse_shift_pdf(uploaded_pdf, valid_keys)
                st.write("### 解析結果")
                for key, info in results.items():
                    if info['max_date'] > 0:
                        st.success(f"【{key}】: 最終日付 {info['max_date']}日 ({info['day_of_week']})")
                    else:
                        st.info(f"【{key}】: データなし")
            except Exception as e:
                st.error(f"解析中にエラーが発生しました: {e}")
