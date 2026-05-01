import streamlit as st
import pandas as pd
import re
import unicodedata
import camelot
import os
from googleapiclient.discovery import build
from google.oauth2 import service_account

# --- 1. Google API 認証 ---
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

# --- 2. 変換・正規化ユーティリティ ---
def normalize_text(text):
    if not isinstance(text, str): return ""
    # 空白削除、NFKC正規化、小文字化
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def convert_num_to_time_str(val):
    """0.25単位を15分刻みの時刻に変換 (6.25 -> 06:15)"""
    try:
        if isinstance(val, (int, float)) or (isinstance(val, str) and re.match(r'^\d+(\.\d+)?$', val)):
            num = float(val)
            hours = int(num)
            minutes = int(round((num - hours) * 60))
            return f"{hours:02d}:{minutes:02d}"
        return str(val)
    except (ValueError, TypeError):
        return str(val)

# --- 3. 時程表抽出ロジック ---
def time_schedule_from_drive(sheets_service, file_id):
    spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=file_id).execute()
    sheets = spreadsheet.get('sheets', [])
    location_data_dic = {}

    for s in sheets:
        title = s.get("properties", {}).get("title")
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=file_id, range=f"'{title}'!A1:Z300").execute()
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

def extract_structured_data(loc_df):
    """見出し行のみ15分刻みに変換し、B列は維持"""
    if loc_df.empty: return loc_df
    key_row = loc_df.iloc[0, :].tolist()
    col_start, col_end = None, len(key_row)

    for c in range(3, len(key_row)):
        if re.match(r'^\d+(\.\d+)?$', str(key_row[c]).strip()):
            col_start = c
            break
    if col_start is None: return loc_df.iloc[:, 0:3]

    for c in range(col_start, len(key_row)):
        val_str = str(key_row[c]).strip()
        if val_str != "" and not re.match(r'^\d+(\.\d+)?$', val_str):
            col_end = c
            break

    base_info = loc_df.iloc[:, 0:3].copy()
    time_data = loc_df.iloc[:, col_start:col_end].copy()

    for col in time_data.columns:
        val_top = time_data.iloc[0].loc[col]
        time_data.iloc[0, time_data.columns.get_loc(col)] = convert_num_to_time_str(val_top)
        if len(time_data) > 1:
            time_data.iloc[1:, time_data.columns.get_loc(col)] = time_data.iloc[1:, time_data.columns.get_loc(col)].astype(str)

    return pd.concat([base_info, time_data], axis=1)

# --- 4. PDF 0列目スキャン (○×判定リスト生成) ---
def scan_pdf_with_debug(pdf_stream, time_dic):
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    debug_list = []
    found_results = []
    matched_keys_set = set()

    try:
        tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice')
        if not tables: return [], pd.DataFrame([{"エラー": "テーブル未検出"}])
        
        pdf_df = tables[0].df
        
        # 文字数が多いKeyから順に判定（T1とTの誤判定防止）
        sorted_keys = sorted(time_dic.keys(), key=len, reverse=True)

        for i in range(len(pdf_df)):
            raw_val = str(pdf_df.iloc[i, 0]).replace('\n', ' ')
            # 数字、曜日、記号を削除（Keyそのものに数字がある場合はここを調整）
            clean_val = re.sub(r'[\d/:()月火水木金土日\s　]', '', raw_val)
            clean_val = normalize_text(clean_val)
            
            hit_key = None
            for k in sorted_keys:
                if k != "" and (k == clean_val or k in clean_val):
                    hit_key = k
                    break
            
            if hit_key:
                status = f"○ ({hit_key})"
                if hit_key not in matched_keys_set:
                    found_results.append({'key': hit_key, 'time_schedule': time_dic[hit_key]})
                    matched_keys_set.add(hit_key)
            else:
                status = "×"

            debug_list.append({
                "行": i + 1,
                "PDF 0列目データ": raw_val,
                "クリーニング後": clean_val,
                "判定": status
            })
                    
    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")
        
    return found_results, pd.DataFrame(debug_list)
