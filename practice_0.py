import streamlit as st
import pandas as pd
import re
import unicodedata
import camelot
import os
import math
from googleapiclient.discovery import build
from google.oauth2 import service_account

# --- 1. 認証・Google Sheets 連携[cite: 1] ---
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
        return build('drive', 'v3', credentials=creds), build('sheets', 'v4', credentials=creds)
    except: return None, None

# --- 2. クリーニング・変換コアロジック[cite: 1, 2] ---
def normalize_text(text):
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def clean_strictly(text):
    """[0,0]から日付(1-31)・曜日を除去したansを生成[cite: 2]"""
    if not isinstance(text, str): return ""
    text = re.sub(r'\b([1-9]|[12][0-9]|3[01])\b', '', text) # 日付除去
    text = re.sub(r'[月火水木金土日()/:：\s　\n]', '', text) # 曜日・記号除去
    return normalize_text(text)

def convert_num_to_time_str(val):
    """0.25単位の数値を時刻(15分刻み)に訂正[cite: 1, 3]"""
    try:
        val_str = str(val).strip()
        if re.match(r'^\d+(\.\d+)?$', val_str):
            num = float(val_str)
            hours = int(num)
            minutes = int(round((num - hours) * 60))
            return f"{hours:02d}:{minutes:02d}"
        return val_str
    except: return str(val)

# --- 3. 時程表（Google Sheets）の取得・辞書登録[cite: 1, 3] ---
def extract_structured_data(loc_df):
    """見出し行(D列以降)の時刻を訂正[cite: 3]"""
    if loc_df.empty: return loc_df
    base_info = loc_df.iloc[:, 0:3].copy() # A-C列[cite: 3]
    time_data = loc_df.iloc[:, 3:].copy()  # D列以降[cite: 3]
    for col in time_data.columns:
        val_top = time_data.iloc[0].loc[col]
        time_data.iloc[0, time_data.columns.get_loc(col)] = convert_num_to_time_str(val_top)
    return pd.concat([base_info, time_data], axis=1)

def time_schedule_from_drive(sheets_service, file_id):
    """勤務地をKeyにしてtime_scheduleを辞書登録[cite: 3]"""
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
            val_a = str(df.iloc[i, 0]).strip() # A列検索[cite: 3]
            if val_a != "":
                if current_key is not None:
                    location_data_dic[normalize_text(current_key)] = extract_structured_data(df.iloc[start_row:i, :])
                current_key, start_row = val_a, i
        if current_key is not None:
            location_data_dic[normalize_text(current_key)] = extract_structured_data(df.iloc[start_row:, :])
    return location_data_dic

# --- 4. PDF解析・座標計算[cite: 2] ---
def analyze_pdf_structure(pdf_stream, master_keys):
    """座標計算(l, h1, h2)とlocation判定[cite: 2]"""
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
    try:
        tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice')
        if not tables: return None
        df = tables[0].df

        # locationの決定[cite: 2]
        ans = clean_strictly(str(df.iloc[0, 0]))
        location = ans
        for k in master_keys:
            if k in ans:
                location = k
                break
        
        # 氏名リスト(2行目以降、1行おき)[cite: 2]
        names = [str(df.iloc[i, 0]).split('\n')[0] for i in range(2, len(df), 2) if str(df.iloc[i, 0]).strip()]
        max_name_len = max([len(n) for n in names]) if names else 0
        
        # 座標計算[cite: 2]
        l = math.ceil(max(len(location), max_name_len))
        h1, h2 = 1.0, 1.0 # 暫定高さ(日付・曜日)
        
        return {
            "df": df, "location": location, "l": l, "h1": h1, "h2": h2,
            "mid_start": (l, math.ceil(h1)),
            "bottom_0_0": (0, math.ceil(h1 + h2))
        }
    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")
