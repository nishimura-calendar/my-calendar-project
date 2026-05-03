import streamlit as st
import pandas as pd
import re
import unicodedata
import camelot
import os
import math
from googleapiclient.discovery import build
from google.oauth2 import service_account

def get_unified_services():
    info = st.secrets.get("gcp_service_account") or dict(st.secrets)
    if not info: return None, None
    try:
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/drive.readonly", "https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        return build('drive', 'v3', credentials=creds), build('sheets', 'v4', credentials=creds)
    except: return None, None

def normalize_text(text):
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

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

def analyze_pdf_full(pdf_stream, master_keys):
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
    try:
        tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice')
        if not tables: return None, pd.DataFrame([{"エラー": "表未検出"}])
        raw_df = tables[0].df

        # [0,0]の生データを取得し、拠点・日付・曜日を分解
        raw_0_0 = str(raw_df.iloc[0, 0]).replace('\n', ' ')
        location = "T1"
        for k in master_keys:
            if k in normalize_text(raw_0_0):
                location = k
                break

        # 正規表現で日付と曜日を抽出
        found_dates = re.findall(r'\b([1-9]|[12][0-9]|3[01])\b', raw_0_0)
        found_days = re.findall(r'[月火水木金土日]', raw_0_0)

        # データ再構成
        final_rows = []
        # 行0: [空白] + 日付リスト
        # 要求通り [0,0] にあたる部分は "" (空白) に設定
        final_rows.append([""] + found_dates)
        
        # 行1: [拠点名] + 曜日リスト[cite: 12]
        # [1,0] に location (T1/T2等) を配置
        final_rows.append([location] + found_days)
        
        max_name_len = len(location)
        # 行2以降: 氏名行と資格行を交互に配置[cite: 12]
        for i in range(2, len(raw_df)):
            cell_0 = str(raw_df.iloc[i, 0]).strip()
            if not cell_0 or "nan" in cell_0.lower(): continue
            
            parts = cell_0.split('\n')
            name = parts[0]
            license = parts[1] if len(parts) > 1 else ""
            
            shift_data = raw_df.iloc[i, 1:].tolist()
            # 氏名行
            final_rows.append([name] + shift_data)
            # 資格行 (直下)
            final_rows.append([license] + [""] * len(shift_data))
            
            max_name_len = max(max_name_len, len(name))

        final_df = pd.DataFrame(final_rows)
        l = math.ceil(max_name_len)
        
        return {"df": final_df, "location": location, "l": l}, pd.DataFrame([{"結果": "[0,0]空白化・構造化完了"}])
    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")
