import streamlit as st
import pandas as pd
import re
import unicodedata
import camelot
import os
import math
from googleapiclient.discovery import build
from google.oauth2 import service_account

# --- 1. 認証周りの修正 ---
def get_unified_services():
    info = None
    if "gcp_service_account" in st.secrets:
        info = st.secrets["gcp_service_account"]
    elif "private_key" in st.secrets:
        info = dict(st.secrets)
    
    if info is None: return None, None
    
    try:
        service_account_info = dict(info)
        creds = service_account.Credentials.from_service_account_info(
            service_account_info, 
            scopes=["https://www.googleapis.com/auth/drive.readonly", "https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        # app.py側が2つの引数を期待しているため、両方返す
        return build('drive', 'v3', credentials=creds), build('sheets', 'v4', credentials=creds)
    except:
        return None, None

def normalize_text(text):
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def clean_strictly(text):
    """[0,0]から拠点Keyを抽出"""
    if not isinstance(text, str): return ""
    text = re.sub(r'\b([1-9]|[12][0-9]|3[01])\b', '', text)
    text = re.sub(r'[月火水木金土日()/:：\s　\n]', '', text)
    return normalize_text(text)

# --- 2. 時程表の読み込み ---
def time_schedule_from_drive(sheets_service, file_id):
    spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=file_id).execute()
    location_data_dic = {}
    for s in spreadsheet.get('sheets', []):
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

# --- 3. PDF解析（日付・曜日・資格の配置強制） ---
def analyze_pdf_full(pdf_stream, master_keys):
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
    try:
        tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice')
        if not tables: return None, pd.DataFrame([{"エラー": "表未検出"}])
        
        raw_df = tables[0].df
        
        # 拠点特定
        ans = clean_strictly(str(raw_df.iloc[0, 0]))
        location = "T1"
        for k in master_keys:
            if k in ans:
                location = k
                break

        # 日付・曜日の抽出ロジック（NaNを許容しない）
        dates = []
        days = []
        for col in range(1, len(raw_df.columns)):
            combined_text = str(raw_df.iloc[0, col]) + "\n" + str(raw_df.iloc[1, col])
            d_match = re.search(r'\b([1-9]|[12][0-9]|3[01])\b', combined_text)
            w_match = re.search(r'[月火水木金土日]', combined_text)
            dates.append(d_match.group(0) if d_match else "")
            days.append(w_match.group(0) if w_match else "")

        # 氏名行と資格行を交互に配置
        final_rows = []
        final_rows.append(["日付"] + dates)      # 0行目
        final_rows.append([location] + days)     # 1行目
        
        max_name_len = len(location)
        for i in range(2, len(raw_df)):
            cell_0 = str(raw_df.iloc[i, 0]).strip()
            if not cell_0 or cell_0 == "nan": continue
            
            # セル内の改行（\n）で氏名と資格を分離
            parts = cell_0.split('\n')
            name = parts[0]
            # 2段目の文字があれば資格として採用、なければ空白
            license = parts[1] if len(parts) > 1 else ""
            
            shift_row = raw_df.iloc[i, 1:].tolist()
            
            # 氏名行を追加 (2行目, 4行目...)
            final_rows.append([name] + shift_row)
            # 資格行を直下に追加 (3行目, 5行目...)
            final_rows.append([license] + [""] * len(shift_row))
            
            max_name_len = max(max_name_len, len(name))

        final_df = pd.DataFrame(final_rows)
        l = math.ceil(max_name_len)
        
        report_df = pd.DataFrame([{
            "拠点": location,
            "座標 l": l,
            "日付行": "抽出完了",
            "資格配置": "氏名の直下に展開"
        }])
        
        return {"df": final_df, "location": location, "l": l}, report_df
    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")
