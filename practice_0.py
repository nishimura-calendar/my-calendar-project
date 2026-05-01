import streamlit as st
import pandas as pd
import re
import unicodedata
import camelot
import os
import calendar
from googleapiclient.discovery import build
from google.oauth2 import service_account

# ==========================================
# 1. 認証とテキスト正規化[cite: 5]
# ==========================================
def get_unified_services():
    """Google DriveおよびSheets APIサービスを構築"""
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

# ==========================================
# 2. 前提情報の取得[cite: 3]
# ==========================================
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
            val = int(n); 
            if 1 <= val <= 12: m = val; break
    return y, m

def get_month_truth(year, month):
    last_day = calendar.monthrange(year, month)[1]
    first_wday_idx = calendar.monthrange(year, month)[0]
    weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    return last_day, weekdays[first_wday_idx]

# ==========================================
# 3. 時程表（スプレッドシート）の動的読み込み[cite: 2, 5]
# ==========================================
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

# ==========================================
# 4. 座標計算と解析メインロジック
# ==========================================
def process_full_logic(pdf_stream, target_staff, time_dic, year, month):
    truth_days, truth_first_wday = get_month_truth(year, month)
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())

    try:
        # 【STEP 1】仮読み込みで座標のヒントを得る
        temp_tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice')
        if not temp_tables: return None, "PDFから表を検出できませんでした。"
        
        # 1ページ目のサイズを取得 (境界指定に必要)
        table = temp_tables[0]
        x1, y1, x2, y2 = table._bbox # 現在の表の外枠

        # 0列目の「最初の改行まで」の最大幅 l を計算
        max_char = len(target_staff)
        for val in table.df.iloc[:, 0].astype(str):
            first_line = val.split('\n')[0].strip()
            if len(first_line) > max_char: max_char = len(first_line)
        l_pt = (max_char * 12) + 15 

        # 【STEP 2】確定座標で本読み込み
        # flavor='lattice' では columns は使えないため、
        # table_areas で表の全域を指定し、罫線の検知に任せます。
        # (エラー回避のため、シンプルに lattice の標準読み込みを適用し、後処理で 0 列目を分割)
        df = table.df

        # 【STEP 3】拠点Key照合
        raw_00 = str(df.iloc[0, 0]).split('\n')[0].strip()
        new_location = re.sub(r'\d{1,2}/\d{1,2}|[（\(][月火水木金土日][）\)]|[月火水木金土日]', '', raw_00).strip()
        
        # 拠点の特定
        matched_key = next((k for k in time_dic.keys() if k in normalize_text(new_location) or normalize_text(new_location) in k), None)
        if not matched_key:
            return None, f"勤務地『{new_location}』の時程表が未定義です。"

        # 【STEP 4】整合性チェック
        pdf_days = len(df.columns) - 1
        pdf_first_wday = ""
        for r in range(min(5, len(df))):
            match = re.search(r'[月火水木金土日]', str(df.iloc[r, 1]))
            if match: pdf_first_wday = match.group(0); break

        if pdf_days != truth_days or pdf_first_wday != truth_first_wday:
            return df, f"【整合性エラー】PDF: {pdf_days}日/{pdf_first_wday}曜始 vs 暦: {truth_days}日/{truth_first_wday}曜始"

        # 【STEP 5】スタッフ抽出
        clean_target = normalize_text(target_staff)
        # 改行の1行目で照合
        search_col = df.iloc[:, 0].astype(str).apply(lambda x: normalize_text(x.split('\n')[0]))
        
        if clean_target not in search_col.values:
            return df, f"『{target_staff}』が見当たりません。"

        idx = search_col[search_col == clean_target].index[0]
        
        return {
            "key": matched_key,
            "my_daily_shift": df.iloc[idx : idx + 2, :].values.tolist(), # 本人2行
            "other_daily_shift": [df.iloc[i].tolist() for i in range(len(df)) if i not in [0, idx, idx+1] and any(str(v).strip() for v in df.iloc[i])],
            "time_schedule_full": time_dic[matched_key] # 全範囲表示[cite: 2]
        }, None

    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")
