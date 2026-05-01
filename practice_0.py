import streamlit as st
import pandas as pd
import re
import unicodedata
import camelot
import os
import calendar
from googleapiclient.discovery import build
from google.oauth2 import service_account

# --- 1. 認証とテキスト正規化 ---
def get_unified_services():
    if "gcp_service_account" in st.secrets:
        info = st.secrets["gcp_service_account"]
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=[
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/spreadsheets.readonly"
            ]
        )
        return build('drive', 'v3', credentials=creds), build('sheets', 'v4', credentials=creds)
    return None, None

def normalize_text(text):
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

# --- 2. ファイル名等からの年月抽出 ---
def extract_year_month_from_text(text):
    if not text: return None, None
    text = unicodedata.normalize('NFKC', text)
    nums = re.findall(r'\d+', text)
    y, m = None, None
    month_match = re.search(r'(\d{1,2})月', text)
    if month_match: m = int(month_match.group(1))
    for n in nums:
        if len(n) == 4: y = int(n)
        elif len(n) == 2 and not y: y = 2000 + int(n)
    if not m:
        for n in nums:
            val = int(n)
            if 1 <= val <= 12: m = val; break
    return y, m

def get_month_truth(year, month):
    last_day = calendar.monthrange(year, month)[1]
    first_wday_idx = calendar.monthrange(year, month)[0]
    weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    return last_day, weekdays[first_wday_idx]

# --- 3. 時程表の読み込み ---
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

# --- 4. 解析メインロジック (座標固定・Key対応版) ---
def process_full_logic(pdf_stream, target_staff, time_dic, year, month):
    truth_days, truth_first_wday = get_month_truth(year, month)
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())

    try:
        # lattice方式で読み込み
        tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice')
        if not tables: return None, "PDFから表を検出できませんでした。"
        df = tables[0].df

        # A. 拠点Keyの特定（[0,0] または [1,0] から T+数字 を含む長い名前を救出）
        cell_00_10 = str(df.iloc[0, 0]) + " " + str(df.iloc[1, 0])
        # T5 や 合衆国_ワシントン_T5 などのパターンに対応
        key_match = re.search(r'[^\s\n]*T\d+[^\s\n]*', cell_00_10)
        found_key = key_match.group(0) if key_match else cell_00_10.split('\n')[0].strip()
        
        matched_key = next((k for k in time_dic.keys() if normalize_text(found_key) in k or k in normalize_text(found_key)), None)
        if not matched_key:
            return df, f"Key『{found_key}』が時程表に見当たりません。"

        # B. 1日の曜日の特定（ご提案通り [1, 1] を確認）
        cell_11 = str(df.iloc[1, 1])
        wday_match = re.search(r'[月火水木金土日]', cell_11)
        pdf_first_wday = wday_match.group(0) if wday_match else "不明"

        # C. 整合性チェック
        if pdf_first_wday != truth_first_wday:
            return df, f"【整合性エラー】PDF:[1,1]は{pdf_first_wday}曜始、暦は{truth_first_wday}曜始です。"

        # D. スタッフ抽出（0列目の1行目のみで判定）
        search_names = df.iloc[:, 0].apply(lambda x: normalize_text(str(x).split('\n')[0]))
        clean_target = normalize_text(target_staff)
        
        if clean_target not in search_names.values:
            return df, f"『{target_staff}』が0列目に見つかりません。"

        idx = search_names[search_names == clean_target].index[0]

        return {
            "key": matched_key,
            "my_daily_shift": df.iloc[idx : idx + 2, :].values.tolist(), # 本人2行
            "other_daily_shift": [df.iloc[i].tolist() for i in range(len(df)) if i not in [0, 1, idx, idx+1] and any(str(v).strip() for v in df.iloc[i])], # 他者1行
            "time_schedule_full": time_dic[matched_key]
        }, None

    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")
