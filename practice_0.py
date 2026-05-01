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

# --- 4. 解析メインロジック (日付[0,1]・曜日[1,1] 固定座標版) ---
def process_full_logic(pdf_stream, target_staff, time_dic, year, month):
    truth_days, truth_first_wday = get_month_truth(year, month)
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())

    try:
        # flavor='lattice' で表構造を維持
        tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice')
        if not tables: return None, "PDFから表を検出できませんでした。"
        df = tables[0].df

        # --- A. 拠点Keyの特定 ---
        # ご提案通り [1, 0] 付近から Key (T2など) を抽出
        header_text = str(df.iloc[0, 0]) + " " + str(df.iloc[1, 0])
        key_match = re.search(r'T\d+', header_text)
        found_key = key_match.group(0) if key_match else "不明"
        
        matched_key = next((k for k in time_dic.keys() if normalize_text(found_key) in k or k in normalize_text(found_key)), None)
        if not matched_key:
            return df, f"Key『{found_key}』が時程表に見当たりません。"

        # --- B. 日付・曜日の抽出 (ご提案の座標固定) ---
        # 期待される [0, 1] が「1」であり、[1, 1] が「期待される第一曜日」かを確認
        pdf_day_one = str(df.iloc[0, 1]).strip()
        pdf_wday_one = str(df.iloc[1, 1]).strip()

        # 抽出した文字列から「曜日(月-日)」と「数字(1)」のみを抽出して正規化
        pdf_day_val = re.search(r'1', pdf_day_one)
        pdf_wday_val = re.search(r'[月火水木金土日]', pdf_wday_one)

        if not pdf_day_val or pdf_day_val.group(0) != "1":
            return df, f"【構造エラー】座標[0,1]から日付「1」を検出できませんでした。(抽出値: {pdf_day_one})"

        extracted_wday = pdf_wday_val.group(0) if pdf_wday_val else "不明"
        
        # --- C. 整合性チェック ---
        if extracted_wday != truth_first_wday:
            return df, f"【整合性エラー】PDF[1,1]は「{extracted_wday}曜」、暦は「{truth_first_wday}曜」です。"

        # --- D. スタッフ抽出 (0列目から名前を検索) ---
        search_names = df.iloc[:, 0].apply(lambda x: normalize_text(str(x).split('\n')[0]))
        clean_target = normalize_text(target_staff)
        
        target_idx = None
        for i, name in enumerate(search_names):
            if clean_target in name and i >= 2: # 日付・曜日行(0,1)以降
                target_idx = i
                break

        if target_idx is None:
            return df, f"『{target_staff}』が0列目に見つかりません。"

        # 本人2行、他者1行のルールで抽出
        return {
            "key": matched_key,
            "my_daily_shift": df.iloc[target_idx : target_idx + 2, :].values.tolist(),
            "other_daily_shift": [df.iloc[i].tolist() for i in range(len(df)) if i not in [0, 1, target_idx, target_idx+1] and any(str(v).strip() for v in df.iloc[i])],
            "time_schedule_full": time_dic[matched_key]
        }, None

    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")
