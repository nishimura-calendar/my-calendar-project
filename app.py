import streamlit as st
import pandas as pd
import camelot
import re
import io
import unicodedata 
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# --- [1] 共通関数 ---
def normalize_text(text):
    normalized = unicodedata.normalize('NFKC', text)
    return re.sub(r'\s+', '', normalized).upper()

# --- [2] PDF解析ロジック ---
def parse_shift_pdf(pdf_file, valid_keys):
    tables = camelot.read_pdf(io.BytesIO(pdf_file.read()), pages='all', flavor='stream')
    # 辞書のキー名を完全に統一
    results = {key: {'max_date': 0, 'day_of_week': "不明"} for key in valid_keys}
    normalized_keys = {normalize_text(k): k for k in valid_keys}
    processed_keys = set()

    for table in tables:
        df = table.df
        current_key = None
        
        for i in range(len(df)):
            row_values = df.iloc[i].astype(str).tolist()
            norm_row = normalize_text(" ".join(row_values))
            
            # キー検索
            found_key = next((orig for norm_k, orig in normalized_keys.items() if norm_k == norm_row), None)
            if found_key:
                current_key = found_key
                continue
            
            # 日付行（数字が並ぶ行）を特定
            if current_key and current_key not in processed_keys:
                nums_in_row = [re.findall(r'\b([1-9]|1[0-9]|2[0-9]|3[01])\b', val) for val in row_values]
                
                if sum(len(n) for n in nums_in_row) >= 5:
                    all_nums = [int(n) for sublist in nums_in_row for n in sublist]
                    if not all_nums: continue
                    
                    max_d = max(all_nums)
                    
                    # 最大日付がある列インデックスを探す
                    target_col_idx = -1
                    for col_idx, nums in enumerate(nums_in_row):
                        if str(max_d) in nums:
                            target_col_idx = col_idx
                            break
                    
                    # 曜日行（直下の行）から取得
                    if target_col_idx != -1 and i + 1 < len(df):
                        day_row = df.iloc[i+1].astype(str).tolist()
                        results[current_key]['max_date'] = max_d
                        raw_day = day_row[target_col_idx]
                        results[current_key]['day_of_week'] = re.sub(r'[\|\s]+', '', raw_day)
                    
                    processed_keys.add(current_key)
    return results

# --- [3] メインUI ---
st.title("シフト解析システム")

# valid_keys取得ロジック（省略部分は既存のものを維持してください）
# ...（load_and_process_dataの呼び出し）...

uploaded_pdf = st.file_uploader("シフト表PDFをアップロード", type="pdf")

if uploaded_pdf:
    # valid_keysは既に定義されている想定
    with st.spinner('解析中...'):
        try:
            results = parse_shift_pdf(uploaded_pdf, valid_keys)
            st.write("### 解析結果")
            for key, info in results.items():
                if info['max_date'] > 0:
                    # ここで辞書のキー名 'day_of_week' を正確に参照
                    st.success(f"【{key}】: 最終日付 {info['max_date']}日 ({info['day_of_week']})")
                else:
                    st.info(f"【{key}】: データなし")
        except Exception as e:
            st.error(f"解析中にエラーが発生しました: {e}")
