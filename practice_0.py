import streamlit as st
import pandas as pd
import re
import unicodedata
from googleapiclient.discovery import build
from google.oauth2 import service_account

# ==========================================
# 1. 認証サービス（app.py から呼び出される関数）
# ==========================================
def get_unified_services():
    """Google APIへの接続を確立"""
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

# ==========================================
# 2. 時間表記の変換 (6.25 -> 6:15)
# ==========================================
def convert_float_to_time(val):
    """数値やその文字列を時間表記に変換。例外時は元の値を返す"""
    try:
        # 文字列の「なし」などはそのまま返す
        if val == "" or val == "なし": return ""
        f_val = float(val)
        hours = int(f_val)
        minutes = int(round((f_val - hours) * 60))
        return f"{hours}:{minutes:02d}"
    except (ValueError, TypeError):
        return val

# ==========================================
# 3. 勤務地ごとの動的列抽出
# ==========================================
def extract_col_range(loc_df):
    """
    D列(index 3)以降を走査し、最初の数値から最後の数値までの範囲を抽出。
    拠点ごとに時間列の数が異なっても対応。
    """
    if loc_df.empty: return loc_df

    header_row = loc_df.iloc[0].tolist()
    num_pattern = re.compile(r'^-?\d+(\.\d+)?$') # 数値判定
    
    # D列以降で数値が入っているインデックスを取得
    num_indices = [
        i for i, val in enumerate(header_row) 
        if i >= 3 and num_pattern.match(str(val).strip())
    ]
    
    if not num_indices:
        # 時間軸が見つからない場合は基本の3列のみ
        return loc_df.iloc[:, 0:3]
    
    col_start = min(num_indices)
    col_end = max(num_indices) + 1
    
    # A-C列 + 特定した時間範囲を結合
    res_df = pd.concat([loc_df.iloc[:, 0:3], loc_df.iloc[:, col_start:col_end]], axis=1)
    
    # 1行目（時間軸）を「6:15」形式に書き換え
    new_header = res_df.iloc[0].tolist()
    for i in range(3, len(new_header)):
        new_header[i] = convert_float_to_time(new_header[i])
    res_df.iloc[0] = new_header
    
    return res_df

# ==========================================
# 4. スプレッドシート読み込み
# ==========================================
def time_schedule_from_drive(sheets_service, file_id):
    """全シートを巡回し、A列をKeyとして拠点データを辞書化"""
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
                    # 拠点ごとに動的範囲を計算して登録
                    location_data_dic[current_key] = extract_col_range(df.iloc[start_row:i, :])
                current_key, start_row = val_a, i
        
        if current_key is not None:
            location_data_dic[current_key] = extract_col_range(df.iloc[start_row:, :])
                
    return location_data_dic
