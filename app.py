import streamlit as st
import pandas as pd
import camelot
import re
import io
import unicodedata 
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# --- [1] 定数・共通関数 ---
def normalize_text(text):
    normalized = unicodedata.normalize('NFKC', text)
    return re.sub(r'\s+', '', normalized).upper()

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

# --- [2] PDF解析ロジック（最初のブロックのみ抽出） ---
def parse_shift_pdf(pdf_file, valid_keys):
    tables = camelot.read_pdf(io.BytesIO(pdf_file.read()), pages='all', flavor='stream')
    results = {key: {'max_date': 0, 'last_day_name': "不明"} for key in valid_keys}
    normalized_keys = {normalize_text(k): k for k in valid_keys}
    processed_keys = set()

    for table in tables:
        df = table.df
        current_key = None
        
        for i in range(len(df)):
            row_values = df.iloc[i].astype(str).tolist()
            norm_row = normalize_text(" ".join(row_values))
            
            # キーが見つかったらその後の行を解析
            found_key = next((orig for norm_k, orig in normalized_keys.items() if norm_k == norm_row), None)
            if found_key:
                current_key = found_key
                continue
            
            if current_key and current_key not in processed_keys:
                # 数字のみを抽出して「日付行」を特定
                nums_in_row = [re.findall(r'\b([1-9]|1[0-9]|2[0-9]|3[01])\b', val) for val in row_values]
                
                # 31のような大きな数字が含まれる行をヘッダーとして処理
                if sum(len(n) for n in nums_in_row) >= 5:
                    # この行にある最大の日付を取得
                    all_nums = [int(n) for sublist in nums_in_row for n in sublist]
                    max_d = max(all_nums)
                    
                    # 曜日行（日付行の次の行）から、最終日付と同じ列にある値を取得
                    # 日付行の各列で、最大日付があるインデックスを探す
                    target_col_idx = -1
                    for col_idx, nums in enumerate(nums_in_row):
                        if str(max_d) in nums:
                            target_col_idx = col_idx
                            break
                    
                    if target_col_idx != -1 and i + 1 < len(df):
                        day_row = df.iloc[i+1].astype(str).tolist()
                        results[current_key]['max_date'] = max_d
                        # 曜日情報を抽出（余計な記号を除去）
                        raw_day = day_row[target_col_idx]
                        results[current_key]['last_day_name'] = re.sub(r'[\|\s]+', '', raw_day)
                    
                    processed_keys.add(current_key)
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
    request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    df = pd.read_excel(fh, header=None, engine='openpyxl', dtype=str)
    return process_data(df)

# --- メイン処理 ---
st.title("シフト解析システム")

# 変数の初期化
valid_keys = []
try:
    data_dict = load_and_process_data()
    valid_keys = list(data_dict.keys())
except Exception as e:
    st.error(f"データ読み込みエラー: {e}")

uploaded_pdf = st.file_uploader("シフト表PDFをアップロード", type="pdf")

if uploaded_pdf:
    if not valid_keys:
        st.error("解析用データが読み込めていないため、シフト表を解析できません。")
    else:
        with st.spinner('解析中...'):
            try:
                results = parse_shift_pdf(uploaded_pdf, valid_keys)
                st.write("### 解析結果")
                for key, info in results.items():
                    if info['max_date'] > 0:
                        st.success(f"【{key}】: 最終日付 {info['max_date']}日 ({info['last_day']}曜日相当)")
                    else:
                        st.info(f"【{key}】: データなし")
            except Exception as e:
                st.error(f"解析中にエラーが発生しました: {e}")
