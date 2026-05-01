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

# --- 2. ファイル名からの年月抽出 ---
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

# --- 3. 時程表（スプレッドシート）の動的読み込み[cite: 2, 5] ---
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

# --- 4. PDF解析メインロジック ---
def process_full_logic(pdf_stream, target_staff, time_dic, year, month):
    # ① 月の日数と1日の曜日を算出
    truth_days = calendar.monthrange(year, month)[1]
    truth_wday_idx = calendar.monthrange(year, month)[0]
    weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    truth_first_wday = weekdays[truth_wday_idx]

    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())

    try:
        # 罫線を生かす lattice 方式
        tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice')
        if not tables: return None, "PDFから表を検出できませんでした。"
        df = tables[0].df

        # ② 0列目検索（new_location特定）
        raw_00 = str(df.iloc[0, 0]).replace('\n', ' ')
        new_location = re.sub(r'\d{1,2}/\d{1,2}|[（\(][月火水木金土日][）\)]|[月火水木金土日]', '', raw_00).strip()
        
        # 拠点Key照合 (第3関門)[cite: 5]
        matched_key = next((k for k in time_dic.keys() if k in normalize_text(new_location) or normalize_text(new_location) in k), None)
        if not matched_key:
            return None, f"このファイルは勤務地『{new_location}』のシフト表です。時程表には未定義です。"

        # ③ 整合性チェック（日数・第一曜日）
        pdf_days = len(df.columns) - 1
        pdf_first_wday = ""
        for r in range(min(3, len(df))):
            match = re.search(r'[月火水木金土日]', str(df.iloc[r, 1]))
            if match: pdf_first_wday = match.group(0); break

        if pdf_days != truth_days or pdf_first_wday != truth_first_wday:
            reason = f"【整合性エラー】PDFは {pdf_days}日/{pdf_first_wday}曜始 ですが、カレンダー上は {truth_days}日/{truth_first_wday}曜始 です。"
            return df, reason

        # ④ 座標設定 (l, h1, h2) の概念適用（latticeによる自動区切りを利用）
        # ⑤ target_staff の検索[cite: 3, 5]
        clean_target = normalize_text(target_staff)
        search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
        if clean_target not in search_col.values:
            return df, f"『{target_staff}』が見当たりません。プログラムを停止します。"

        idx = search_col[search_col == clean_target].index[0]
        
        # ⑥ データ抽出
        my_daily = df.iloc[idx : idx + 2, :].values.tolist() # 本人2行[cite: 5]
        
        others_list = []
        for oi in range(len(df)):
            if oi not in [0, idx, idx + 1]: # ヘッダーと本人分を除外
                row = df.iloc[oi, :].values.tolist()
                if any(str(v).strip() for v in row): others_list.append(row) # 他者各1行[cite: 3]

        return {
            "key": matched_key,
            "my_daily_shift": my_daily,
            "other_daily_shift": others_list,
            "time_schedule_full": time_dic[matched_key] # 行列範囲すべてを表示
        }, None

    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")
