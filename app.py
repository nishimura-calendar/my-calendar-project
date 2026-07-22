import streamlit as st
import pandas as pd
import camelot
import re
import io
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# --- [1] 辞書登録ロジック (既存維持) ---
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

# --- [2] <1> (1)(2)(3) 統合PDF解析 ---
def parse_shift_pdf(pdf_file, valid_keys):
    """
    Keyを第1関門としてPDFブロックを解析し、最大日付・曜日を抽出する
    """
    tables = camelot.read_pdf(io.BytesIO(pdf_file.read()), pages='all', flavor='stream')
    full_df = pd.concat([t.df for t in tables], ignore_index=True)
    
    results = {key: {'max_date': 0, 'last_day': None} for key in valid_keys}
    date_pattern = re.compile(r'\b([12]?\d|3[01])\b')
    weekday_pattern = re.compile(r'[月火水木金土日]')
    current_key = None
    
    for _, row in full_df.iterrows():
        row_str = " ".join([str(v) for v in row]).replace('\n', ' ').strip()
        
        # (1) & (2) Key検知と第1関門（ヘッダー行チェック）
        found_key = next((k for k in valid_keys if k in row_str), None)
        if found_key:
            current_key = found_key
            continue
            
        # (3) 最終日付・曜日の最大値抽出
        if current_key:
            dates = [int(d) for d in date_pattern.findall(row_str)]
            weekdays = weekday_pattern.findall(row_str)
            if dates:
                max_d_in_row = max(dates)
                day_in_row = weekdays[0] if weekdays else None
                if max_d_in_row > results[current_key]['max_date']:
                    results[current_key]['max_date'] = max_d_in_row
                    results[current_key]['last_day'] = day_in_row
    return results

# メイン処理の統合イメージ
# data_dict = process_data(df) # 時程表からKeyと詳細な辞書が完成
# pdf_results = parse_shift_pdf(uploaded_pdf, data_dict.keys()) # これで[1][2]完了
