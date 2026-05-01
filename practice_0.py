import streamlit as st
import pandas as pd
import re
import unicodedata
import camelot
import os
from googleapiclient.discovery import build
from google.oauth2 import service_account

# --- 認証・正規化 (変更なし) ---
def get_unified_services():
    if "gcp_service_account" in st.secrets:
        info = st.secrets["gcp_service_account"]
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/drive.readonly", "https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        return build('drive', 'v3', credentials=creds), build('sheets', 'v4', credentials=creds)
    return None, None

def normalize_text(text):
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

# --- 時刻変換ロジック (6 -> 6:00, 6.25 -> 6:15) ---
def convert_num_to_time_str(val):
    """
    数値(float/int)を HH:MM 形式の文字列に変換する
    例: 6 -> '06:00', 6.25 -> '06:15', 18.5 -> '18:30'
    """
    try:
        # 数値、または数値として解釈できる文字列の場合
        num = float(val)
        hours = int(num)
        minutes = int(round((num - hours) * 60))
        return f"{hours:02d}:{minutes:02d}"
    except (ValueError, TypeError):
        return str(val)

# --- 行列抽出ロジック ---
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
                    location_data_dic[normalize_text(current_key)] = extract_by_key_row_v2(df.iloc[start_row:i, :])
                current_key, start_row = val_a, i
        
        if current_key is not None:
            location_data_dic[normalize_text(current_key)] = extract_by_key_row_v2(df.iloc[start_row:, :])
                
    return location_data_dic

def extract_by_key_row_v2(loc_df):
    """
    勤務地行(0行目)のD列(index 3)以降を検索。
    数値がヒットしてから、文字列が現れるまでを時間列として抽出・変換する。
    """
    key_row = loc_df.iloc[0, :].tolist()
    col_start = None
    col_end = len(key_row)

    # 1. D列(3)以降で、最初に「数値」がヒットする列を探す[cite: 7, 8]
    for c in range(3, len(key_row)):
        val_str = str(key_row[c]).strip()
        if re.match(r'^\d+(\.\d+)?$', val_str): # 正の数値(整数/小浮動小数)にマッチ
            col_start = c
            break

    if col_start is None:
        # 数値列が見つからない場合はA-C列のみ返す
        return loc_df.iloc[:, 0:3]

    # 2. 数値がヒットした後の列で、最初に「純粋な文字列」が現れる列を探す[cite: 7, 8]
    for c in range(col_start, len(key_row)):
        val_str = str(key_row[c]).strip()
        # 空白でなく、かつ数値ではない場合を「文字列が現れた」と判定
        if val_str != "" and not re.match(r'^\d+(\.\d+)?$', val_str):
            col_end = c
            break

    # 3. A-C列 と 特定した時間範囲を結合
    base_info = loc_df.iloc[:, 0:3]
    time_data = loc_df.iloc[:, col_start:col_end].copy()

    # 4. 時間データの全セルに時刻変換を適用 (6 -> 06:00)
    for col in time_data.columns:
        time_data[col] = time_data[col].apply(convert_num_to_time_str)

    return pd.concat([base_info, time_data], axis=1)

# --- PDF解析 (変更なし) ---
def get_key_and_schedule(pdf_stream, time_dic):
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
    try:
        tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice')
        if not tables: return None
        df = tables[0].df
        raw_val = df.iloc[0, 0]
        pdf_key = normalize_text(re.sub(r'[\d/:()月火水木金土日]', '', str(raw_val)))
        matched_key = next((k for k in time_dic.keys() if pdf_key in k or k in pdf_key), None)
        if matched_key:
            return {'key': matched_key, 'time_schedule': time_dic[matched_key], 'raw': raw_val}
    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")
    return None
