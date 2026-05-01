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

# --- 2. 暦情報の取得 ---
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

# --- 4. 解析メインロジック ([1,0]=Key 対応版) ---
def process_full_logic(pdf_stream, target_staff, time_dic, year, month):
    truth_days, truth_first_wday = get_month_truth(year, month)
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())

    try:
        tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice')
        if not tables: return None, "PDFから表を検出できませんでした。"
        df = tables[0].df

        # 【改善】A. 拠点Keyの特定: [1,0] を起点として抽出
        # [1,0] もしくは [0,0] に含まれる T+数字 (例: T2, ワシントン_T5) を取得
        raw_key_area = str(df.iloc[1, 0]) if len(df) > 1 else str(df.iloc[0, 0])
        key_match = re.search(r'T\d+', raw_key_area)
        found_key_id = key_match.group(0) if key_match else normalize_text(raw_key_area)
        
        # マスターデータのKey（シート名やA列の項目）と照合
        matched_key = next((k for k in time_dic.keys() if found_key_id in k or k in found_key_id), None)
        
        if not matched_key:
            return df, f"Key『{found_key_id}』に対応する時程表が見つかりません。(PDF[1,0]: {raw_key_area})"

        # 【改善】B. 第一曜日の特定: 1列目(1日の列)から動的に取得
        pdf_first_wday = ""
        for r in range(min(5, len(df))):
            cell_val = str(df.iloc[r, 1])
            w_match = re.search(r'[月火水木金土日]', cell_val)
            if w_match:
                pdf_first_wday = w_match.group(0)
                break
        
        if pdf_first_wday != truth_first_wday:
            return df, f"【整合性エラー】PDFは{pdf_first_wday}曜始、暦は{truth_first_wday}曜始です。"

        # C. スタッフ抽出
        search_col = df.iloc[:, 0].astype(str).apply(lambda x: normalize_text(x))
        clean_target = normalize_text(target_staff)
        target_idx = next((i for i, val in enumerate(search_col) if clean_target in val and i >= 1), None)

        if target_idx is None:
            return df, f"『{target_staff}』が0列目に見つかりません。"

        return {
            "key": matched_key,
            "my_daily_shift": df.iloc[target_idx : target_idx + 2, :].values.tolist(),
            "other_daily_shift": [df.iloc[i].tolist() for i in range(len(df)) if i not in [0, 1, target_idx, target_idx+1] and any(str(v).strip() for v in df.iloc[i])],
            "time_schedule_full": time_dic[matched_key]
        }, None

    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")
