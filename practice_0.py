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

# --- 4. 解析メインロジック (改行による名前列の圧縮 & 座標固定版) ---
def process_full_logic(pdf_stream, target_staff, time_dic, year, month):
    truth_days, truth_first_wday = get_month_truth(year, month)
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())

    try:
        # split_text=True を指定することで、セル内の改行を検知しやすくします
        tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice', split_text=True)
        if not tables: return None, "PDFから表を検出できませんでした。"
        df = tables[0].df

        # --- A. 拠点Keyの特定 ([1, 0] を基準に Key を抽出) ---
        # 0列目の上部から T+数字 (例: T2) を探す
        header_text = " ".join(df.iloc[0:2, 0].astype(str))
        key_match = re.search(r'T\d+', header_text)
        found_key = key_match.group(0) if key_match else "不明"
        
        matched_key = next((k for k in time_dic.keys() if normalize_text(found_key) in k or k in normalize_text(found_key)), None)
        if not matched_key:
            return df, f"Key『{found_key}』が時程表に見当たりません。"

        # --- B. 座標固定による日付・曜日の特定 ---
        # [0, 1] = 日付 "1", [1, 1] = 第一曜日
        pdf_day_one = str(df.iloc[0, 1]).strip()
        pdf_wday_one = str(df.iloc[1, 1]).strip()

        # 抽出（ノイズ除去）
        pdf_day_val = re.search(r'1', pdf_day_one)
        pdf_wday_val = re.search(r'[月火水木金土日]', pdf_wday_one)

        if not pdf_day_val:
            return df, f"【構造エラー】座標[0,1]に日付「1」が見つかりません。(取得値: {pdf_day_one})"
        
        extracted_wday = pdf_wday_val.group(0) if pdf_wday_val else "不明"
        
        # 整合性チェック
        if extracted_wday != truth_first_wday:
            return df, f"【整合性エラー】PDF[1,1]は「{extracted_wday}曜」、暦は「{truth_first_wday}曜」です。"

        # --- C. 名前列の「改行」を考慮したスタッフ抽出 ---
        # 嵯峨根美智子さんのように「名前\n資格」となっている場合、
        # 改行で分割して「最初の1行（名前）」だけで照合を行う
        search_names = df.iloc[:, 0].apply(lambda x: normalize_text(str(x).split('\n')[0]))
        clean_target = normalize_text(target_staff)
        
        target_idx = None
        for i, name in enumerate(search_names):
            if clean_target in name and i >= 2:
                target_idx = i
                break

        if target_idx is None:
            return df, f"『{target_staff}』が見つかりません。名前列の改行処理を確認してください。"

        # D. 結果の返却（本人2行、他者1行）[cite: 3]
        return {
            "key": matched_key,
            "my_daily_shift": df.iloc[target_idx : target_idx + 2, :].values.tolist(),
            "other_daily_shift": [df.iloc[i].tolist() for i in range(len(df)) if i not in [0, 1, target_idx, target_idx+1] and any(str(v).strip() for v in df.iloc[i])],
            "time_schedule_full": time_dic[matched_key]
        }, None

    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")
