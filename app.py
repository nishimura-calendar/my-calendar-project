import streamlit as st
import pandas as pd
import camelot
import re
import io
import unicodedata 
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

# 【正規化用ヘルパー関数】
def normalize_text(text):
    # 1. 全角→半角などの正規化 (NFKC)
    # 2. 空白・改行の削除
    # 3. 大文字統一（念のため）
    normalized = unicodedata.normalize('NFKC', text)
    return re.sub(r'\s+', '', normalized).upper()

def parse_shift_pdf(pdf_file, valid_keys):
    tables = camelot.read_pdf(io.BytesIO(pdf_file.read()), pages='all', flavor='stream')
    # 結果の初期化（max_dateを0で初期化）
    results = {key: {'max_date': 0, 'last_day': None} for key in valid_keys}
    normalized_keys = {normalize_text(k): k for k in valid_keys}

    for table in tables:
        df = table.df
        current_key = None
        
        for i in range(len(df)):
            row_values = df.iloc[i].astype(str).tolist()
            norm_row = normalize_text(" ".join(row_values))
            
            # ① ヘッダー検索（現在の行がキーと完全一致するか）
            found_key = next((orig for norm_k, orig in normalized_keys.items() if norm_k == norm_row), None)
            if found_key:
                current_key = found_key
                continue
            
            # ② 日付と曜日の探索
            if current_key:
                # 行内の数字を探す
                for col_idx, val in enumerate(row_values):
                    # 「1〜31」の数字のみ抽出
                    nums = re.findall(r'\b([12]?[0-9]|3[01])\b', val)
                    if nums:
                        current_num = int(nums[0])
                        
                        # 数字があった場合、その直後の行（または同行）に曜日がないか探索
                        # (同じ行または次の行に曜日があるケースを想定)
                        target_rows = [i, i+1] 
                        found_day = None
                        for r in target_rows:
                            if r < len(df):
                                cell_val = str(df.iloc[r, col_idx])
                                match = re.search(r'[月火水木金土日]', cell_val)
                                if match:
                                    found_day = match.group()
                                    break
                        
                        # 最大値比較ロジック
                        if current_num >= results[current_key]['max_date']:
                            results[current_key]['max_date'] = current_num
                            if found_day:
                                results[current_key]['last_day'] = found_day
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
