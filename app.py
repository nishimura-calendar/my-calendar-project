import streamlit as st
import pandas as pd
import camelot
import re
import io
import unicodedata 
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# --- [1] 共通処理 ---
def normalize_text(text):
    normalized = unicodedata.normalize('NFKC', text)
    return re.sub(r'\s+', '', normalized).upper()

# --- [2] PDF解析ロジック (最初のブロックのみ走査) ---
def parse_shift_pdf(pdf_file, valid_keys):
    tables = camelot.read_pdf(io.BytesIO(pdf_file.read()), pages='all', flavor='stream')
    # max_date と last_day で管理する構造
    results = {key: {'max_date': 0, 'last_day': None} for key in valid_keys}
    normalized_keys = {normalize_text(k): k for k in valid_keys}

    for table in tables:
        df = table.df
        current_key = None
        
        for i in range(len(df)):
            row_values = df.iloc[i].astype(str).tolist()
            norm_row = normalize_text(" ".join(row_values))
            
            # キーの検索
            found_key = next((orig for norm_k, orig in normalized_keys.items() if norm_k == norm_row), None)
            if found_key:
                current_key = found_key
                continue
            
            # 日付ヘッダー（数字が5つ以上並ぶ行）を検知
            if current_key:
                nums_in_row = [re.findall(r'\b([1-9]|1[0-9]|2[0-9]|3[01])\b', val) for val in row_values]
                
                if sum(len(n) for n in nums_in_row) >= 5:
                    if i + 1 < len(df):
                        data_row = df.iloc[i + 1].astype(str).tolist()
                        for col_idx, nums in enumerate(nums_in_row):
                            for num_str in nums:
                                date_val = int(num_str)
                                # 最大値を更新
                                if date_val >= results[current_key]['max_date']:
                                    results[current_key]['max_date'] = date_val
                                    val = data_row[col_idx]
                                    results[current_key]['last_day'] = re.sub(r'[\|\s]+', '', val)
                        
                        # 最初のブロックで処理が完了したら、そのキーの探索を終了する処理を入れるとより確実です
                        # 今回はシンプルに全走査して最大値を残す形式を維持します
    return results

# --- [3] メインUI ---
st.title("シフト解析システム")

# (Google連携ロジック等は省略...既存のものをそのままお使いください)

uploaded_pdf = st.file_uploader("シフト表PDFをアップロード", type="pdf")

if uploaded_pdf:
    with st.spinner('解析中...'):
        # valid_keys は事前取得済みと想定
        results = parse_shift_pdf(uploaded_pdf, valid_keys)
        
        st.write("### 解析結果")
        for key, info in results.items():
            # 辞書構造に合わせ、info['max_date'] を参照するように修正
            if info['max_date'] > 0:
                st.success(f"【{key}】: 最終日付 {info['max_date']}日 ({info['last_day']}曜日相当)")
            else:
                st.info(f"【{key}】: データなし")
