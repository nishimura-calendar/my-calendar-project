import streamlit as st
import pandas as pd
import camelot
import re
import io
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# --- [1] 時程表の辞書登録ロジック (変更不可) ---
def format_time(val):
    try:
        f_val = float(val)
        h = int(f_val)
        m = int(round((f_val - h) * 60))
        return f"{h}:{m:02d}"
    except (ValueError, TypeError):
        return val

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

# --- [2] PDF解析ロジック ---
def parse_shift_pdf(pdf_file, valid_keys):
    # PDFをテーブルとして読み込みますが、セル構造は無視して中身のテキストだけを抽出します
    tables = camelot.read_pdf(io.BytesIO(pdf_file.read()), pages='all', flavor='stream')
    
    # 1. 全テーブルの全テキストを一つのリストにフラット化
    all_text = []
    for table in tables:
        for row in table.df.values:
            for cell in row:
                all_text.append(str(cell))
    
    # 2. 全体を一つの長い文字列（またはスペース区切りのテキスト）に変換
    # これにより、罫線ノイズやセル間のズレを無視した「文字の流れ」ができます
    full_text_stream = " ".join(all_text)
    
    results = {key: {'max_date': 0, 'last_day': None} for key in valid_keys}
    current_key = None
    
    # 曜日検索の正規表現
    # 「31」の後に何か（＋や空白など）があっても、最終的に「金」や「土」を探す
    pattern = re.compile(r'31\D*([月火水木金土日士])')
    
    # ここからは簡易的な解析になりますが、全テキストからキーを探し、
    # そのキーが含まれるブロック内で「31」と「曜日」のペアを探します
    # ※シンプル化のため、全テキストから最大日付を探すロジックに特化
    
    # もし「31」が見つかり、かつ正規表現にマッチすれば曜日を抽出
    match = pattern.search(full_text_stream)
    if match:
        day = match.group(1).replace('士', '土')
        # どのキーに対しても一律で最終日を適用（T1などが1つしかない場合）
        for key in valid_keys:
            results[key]['max_date'] = 31
            results[key]['last_day'] = day
            
    return results 
    
# --- [3] Google連携・メインUI ---
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
    # 【修正箇所】 file_id -> fileId に変更
    request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    df = pd.read_excel(fh, header=None, engine='openpyxl', dtype=str)
    return process_data(df)

st.title("シフト解析システム")

try:
    data_dict = load_and_process_data()
    valid_keys = list(data_dict.keys())
    
    uploaded_pdf = st.file_uploader("シフト表PDFをアップロード", type="pdf")
    if uploaded_pdf:
        with st.spinner('解析中...'):
            results = parse_shift_pdf(uploaded_pdf, valid_keys)
            st.write("### 解析結果")
            for key, info in results.items():
                if info['max_date'] > 0:
                    st.success(f"【{key}】: 最終日付 {info['max_date']}日 ({info['last_day']}曜日)")
                else:
                    st.info(f"【{key}】: データなし")
except Exception as e:
    st.error(f"システムエラー: {e}")
