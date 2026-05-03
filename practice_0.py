import streamlit as st
import pandas as pd
import re
import unicodedata
import camelot
import os
import math
from googleapiclient.discovery import build
from google.oauth2 import service_account

# --- 1. 認証 (戻り値を2つに固定) ---
def get_unified_services():
    info = st.secrets.get("gcp_service_account") or dict(st.secrets)
    if not info: return None, None
    try:
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/drive.readonly", "https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        # app.py側の drive, sheets = p0.get_unified_services() に対応
        return build('drive', 'v3', credentials=creds), build('sheets', 'v4', credentials=creds)
    except:
        return None, None

def normalize_text(text):
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

# --- 2. 時程表読み込み ---
def time_schedule_from_drive(sheets_service, file_id):
    spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=file_id).execute()
    location_data_dic = {}
    for s in spreadsheet.get('sheets', []):
        title = s.get("properties", {}).get("title")
        res = sheets_service.spreadsheets().values().get(spreadsheetId=file_id, range=f"'{title}'!A1:Z300").execute()
        vals = res.get('values', [])
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

# --- 3. PDF解析 (0,0分解・資格配置) ---
def analyze_pdf_full(pdf_stream, master_keys):
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
    try:
        tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice')
        if not tables: return None, pd.DataFrame([{"エラー": "表未検出"}])
        raw_df = tables[0].df

        # [0,0]から拠点を特定し[1,0]の値とする
        raw_0_0 = str(raw_df.iloc[0, 0]).replace('\n', ' ')
        location = "T1"
        for k in master_keys:
            if k in normalize_text(raw_0_0):
                location = k
                break

        # [0,0]のデータ分解ルール:
        # 日付: [0,0]から location と 曜日 を除いたもの
        # 曜日: [0,0]から location と 日付 を除いたもの
        found_dates = re.findall(r'\b([1-9]|[12][0-9]|3[01])\b', raw_0_0)
        found_days = re.findall(r'[月火水木金土日]', raw_0_0)

        # データ再構成
        final_rows = []
        # 行0: 日付行
        final_rows.append(["日付"] + found_dates)
        # 行1: 曜日行 (先頭に拠点名)[cite: 12]
        final_rows.append([location] + found_days)
        
        max_name_len = len(location)
        # 行2以降: 氏名とその直下に資格[cite: 12]
        for i in range(2, len(raw_df)):
            cell_0 = str(raw_df.iloc[i, 0]).strip()
            if not cell_0 or "nan" in cell_0.lower(): continue
            
            parts = cell_0.split('\n')
            name = parts[0]
            license = parts[1] if len(parts) > 1 else ""
            
            shift_data = raw_df.iloc[i, 1:].tolist()
            # 氏名行
            final_rows.append([name] + shift_data)
            # 資格行 (1行下)[cite: 12]
            final_rows.append([license] + [""] * len(shift_data))
            
            max_name_len = max(max_name_len, len(name))

        final_df = pd.DataFrame(final_rows)
        l = math.ceil(max_name_len)
        
        return {"df": final_df, "location": location, "l": l}, pd.DataFrame([{"結果": "日付・曜日・資格の構造化完了"}])
    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")
