import streamlit as st
import pandas as pd
import re
import unicodedata
import camelot
import os
import math
from googleapiclient.discovery import build
from google.oauth2 import service_account

# --- 1. Google Sheets 連携 ---
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
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        return build('drive', 'v3', credentials=creds), build('sheets', 'v4', credentials=creds)
    except: return None, None

def normalize_text(text):
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def clean_strictly(text):
    """[0,0]から日付(1-31)・曜日を除去し拠点Keyを抽出[cite: 2, 11]"""
    if not isinstance(text, str): return ""
    text = re.sub(r'\b([1-9]|[12][0-9]|3[01])\b', '', text) 
    text = re.sub(r'[月火水木金土日()/:：\s　\n]', '', text) 
    return normalize_text(text)

def convert_num_to_time_str(val):
    """0.25単位の数値を時刻(15分刻み)に訂正"""
    try:
        val_str = str(val).strip()
        if re.match(r'^\d+(\.\d+)?$', val_str):
            num = float(val_str)
            hours = int(num)
            minutes = int(round((num - hours) * 60))
            return f"{hours:02d}:{minutes:02d}"
        return val_str
    except: return str(val)

# --- 2. 時程表の取得・時刻訂正 ---
def extract_structured_data(loc_df):
    """見出し行の数値を時刻表示に訂正[cite: 3, 11]"""
    if loc_df.empty: return loc_df
    base_info = loc_df.iloc[:, 0:3].copy()
    time_data = loc_df.iloc[:, 3:].copy()
    for col in time_data.columns:
        raw_value = time_data.iloc[0].loc[col]
        time_data.iloc[0, time_data.columns.get_loc(col)] = convert_num_to_time_str(raw_value)
    return pd.concat([base_info, time_data], axis=1)

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
                    location_data_dic[normalize_text(current_key)] = extract_structured_data(df.iloc[start_row:i, :])
                current_key, start_row = val_a, i
        if current_key is not None:
            location_data_dic[normalize_text(current_key)] = extract_structured_data(df.iloc[start_row:, :])
    return location_data_dic

# --- 3. PDF解析 (座標計算・拠点配置) ---
def analyze_pdf_full(pdf_stream, time_dic):
    """[cite: 2, 9, 10, 11]"""
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
    try:
        tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice')
        if not tables: return None, pd.DataFrame([{"エラー": "表未検出"}])
        
        df = tables[0].df
        raw_0_0 = str(df.iloc[0, 0])
        ans = clean_strictly(raw_0_0)
        
        # 拠点特定
        location = "不明"
        for key in time_dic.keys():
            if key in ans:
                location = key
                break
        if location == "不明": location = ans if ans else "T1"
        
        # 修正指示：[1,0]にlocationを配置
        df.iloc[1, 0] = location

        # 氏名リスト取得(2行目から1行おき)と座標lの算出
        names = [str(df.iloc[i, 0]).split('\n')[0] for i in range(2, len(df), 2) if str(df.iloc[i, 0]).strip()]
        max_name_len = max([len(n) for n in names]) if names else 0
        l = math.ceil(max(len(location), max_name_len))
        
        report_df = pd.DataFrame([{
            "対象セル": "[0,0]解析 → [1,0]配置",
            "抽出拠点": location,
            "算出座標 l": l,
            "判定": "○ 照合完了" if normalize_text(location) in time_dic else "× 未登録"
        }])
        
        return {"df": df, "location": location, "l": l}, report_df
    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")
