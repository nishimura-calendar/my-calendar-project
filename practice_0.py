import streamlit as st
import pandas as pd
import re
import unicodedata
import camelot
import os
import calendar
from googleapiclient.discovery import build
from google.oauth2 import service_account

# --- 1. 共通処理・正規化 ---
def get_unified_services():
    if "gcp_service_account" in st.secrets:
        info = st.secrets["gcp_service_account"]
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/drive.readonly", "https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        return build('drive', 'v3', credentials=creds), build('sheets', 'v4', credentials=creds)
    return None, None

def normalize_text(text):
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def get_month_truth(year, month):
    last_day = calendar.monthrange(year, month)[1]
    first_wday_idx = calendar.monthrange(year, month)[0]
    weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    return last_day, weekdays[first_wday_idx]

# --- 2. 時程表マスター読込 ---
def time_schedule_from_drive(sheets_service, file_id):
    spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=file_id).execute()
    sheets = spreadsheet.get('sheets', [])
    location_data_dic = {}
    for s in sheets:
        title = s.get("properties", {}).get("title")
        result = sheets_service.spreadsheets().values().get(spreadsheetId=file_id, range=f"'{title}'!A1:Z300").execute()
        vals = result.get('values', [])
        if not vals: continue
        df = pd.DataFrame(vals).fillna('')
        current_key, start_row = None, 0
        for i in range(len(df)):
            val_a = str(df.iloc[i, 0]).strip()
            if val_a != "":
                if current_key is not None:
                    location_data_dic[normalize_text(current_key)] = df.iloc[start_row:i, :]
                current_key, start_row = val_a, i
        if current_key is not None:
            location_data_dic[normalize_text(current_key)] = df.iloc[start_row:, :]
    return location_data_dic

# --- 3. メイン解析ロジック ---
def process_full_logic(pdf_stream, target_staff, time_dic, year, month):
    truth_days, truth_first_wday = get_month_truth(year, month)
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())

    try:
        # split_text=True でセル内の改行を保持
        tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice', split_text=True)
        if not tables: return None, "PDFから表を検出できませんでした。"
        df = tables[0].df

        # A. Keyの特定 ( [1,0] を優先、なければ吸い込まれた [0,0] から探す )
        key_search_area = str(df.iloc[1, 0]) + " " + str(df.iloc[0, 0])
        key_match = re.search(r'T\d+', key_search_area)
        found_key = key_match.group(0) if key_match else "不明"
        
        matched_key = next((k for k in time_dic.keys() if found_key in k or k in found_key), None)
        if not matched_key:
            return df, f"拠点Key『{found_key}』がマスターに見当たりません。"

        # B. 日付・曜日の「定規」確認 ([0,1]の日付 と [1,1]の曜日)[cite: 2]
        pdf_day_one = re.sub(r'\D', '', str(df.iloc[0, 1]))
        pdf_wday_one = re.search(r'[月火水木金土日]', str(df.iloc[1, 1]))
        
        extracted_wday = pdf_wday_one.group(0) if pdf_wday_one else "不明"

        # 整合性チェック
        if extracted_wday != truth_first_wday:
            return df, f"【整合性エラー】PDF[1,1]は「{extracted_first_wday}曜」、暦は「{truth_first_wday}曜」です。"

        # C. 名前と資格の「2行分割」スキャン
        clean_target = normalize_text(target_staff)
        target_idx = None
        
        # 0列目を走査
        for i in range(len(df)):
            cell_val = str(df.iloc[i, 0])
            # 改行で分割して1行目（名前）を確認
            parts = cell_val.split('\n')
            if clean_target in normalize_text(parts[0]) and i >= 2:
                target_idx = i
                break

        if target_idx is None:
            return df, f"『{target_staff}』が見つかりません。"

        # D. 本人のシフト (名前行と資格行の2行を抽出)
        my_shift = []
        for offset in [0, 1]:
            row_data = df.iloc[target_idx + offset].tolist()
            # セル内の改行を処理して表示用に見栄えを整える
            my_shift.append(row_data)

        # E. 他者のシフト (ヘッダーと本人以外を1行ずつ)
        other_shifts = []
        for i in range(2, len(df)):
            if i != target_idx and i != target_idx + 1:
                row = df.iloc[i].tolist()
                if any(str(v).strip() for v in row):
                    other_shifts.append(row)

        return {
            "key": matched_key,
            "my_daily_shift": my_shift,
            "other_daily_shift": other_shifts,
            "time_schedule_full": time_dic[matched_key]
        }, None

    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")

def extract_year_month_from_text(text):
    text = unicodedata.normalize('NFKC', text)
    nums = re.findall(r'\d+', text)
    y, m = None, None
    month_match = re.search(r'(\d{1,2})月', text)
    if month_match: m = int(month_match.group(1))
    for n in nums:
        if len(n) == 4: y = int(n)
        elif len(n) == 2 and not y: y = 2000 + int(n)
    return y, m
