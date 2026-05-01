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

# --- 4. 解析メインロジック (第一曜日を動的に特定) ---
def process_full_logic(pdf_stream, target_staff, time_dic, year, month):
    # カレンダー上の正解（期待値）を取得
    truth_days, truth_first_wday = get_month_truth(year, month)
    
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())

    try:
        tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice')
        if not tables: return None, "PDFから表を検出できませんでした。"
        df = tables[0].df

        # A. 拠点Keyの特定 ([1,0]付近を優先)
        header_area = " ".join(df.iloc[0:3, 0].astype(str))
        key_match = re.search(r'[^\s\n]*T\d+[^\s\n]*', header_area)
        found_key = key_match.group(0) if key_match else "不明"
        
        matched_key = next((k for k in time_dic.keys() if normalize_text(found_key) in k or k in normalize_text(found_key)), None)
        if not matched_key:
            return df, f"Key『{found_key}』が時程表に見当たりません。"

        # B. 【改善】1列目から「第一曜日」を動的に見つける
        pdf_first_wday = ""
        # 1日の列（index=1）を上から走査
        for r in range(len(df)):
            cell_val = str(df.iloc[r, 1])
            # セル内に「月〜日」のいずれかが含まれているか
            wday_match = re.search(r'[月火水木金土日]', cell_val)
            if wday_match:
                # 最初に見つかった曜日を「第一曜日」とする
                pdf_first_wday = wday_match.group(0)
                break
        
        # C. 整合性チェック (抽出した第一曜日 vs カレンダーの正解)
        if pdf_first_wday != truth_first_wday:
            return df, f"【整合性エラー】PDFの1日目は「{pdf_first_wday}曜日」と解析されましたが、暦では「{truth_first_wday}曜日」です。"

        # D. スタッフ抽出 (0列目の1行目のみで判定)
        search_names = df.iloc[:, 0].apply(lambda x: normalize_text(str(x).split('\n')[0]))
        clean_target = normalize_text(target_staff)
        
        target_idx = None
        for i, name in enumerate(search_names):
            if clean_target in name and i >= 1:
                target_idx = i
                break

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
