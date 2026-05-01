import streamlit as st
import pandas as pd
import re
import unicodedata
import camelot
import os
from googleapiclient.discovery import build
from google.oauth2 import service_account

# --- 1. Google API 認証サービス ---
def get_unified_services():
    """GCPサービスアカウントを使用してDriveとSheetsのサービスを構築"""
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

# --- 2. ユーティリティ・変換関数 ---
def normalize_text(text):
    """テキスト正規化（空白削除、NFKC正規化、小文字化）"""
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def convert_num_to_time_str(val):
    """
    0.25単位の数値を時刻形式に変換
    例: 6 -> 06:00, 6.25 -> 06:15, 6.5 -> 06:30, 6.75 -> 06:45
    """
    try:
        if isinstance(val, (int, float)) or (isinstance(val, str) and re.match(r'^\d+(\.\d+)?$', val)):
            num = float(val)
            hours = int(num)
            minutes = int(round((num - hours) * 60))
            return f"{hours:02d}:{minutes:02d}"
        return str(val)
    except (ValueError, TypeError):
        return str(val)

# --- 3. スプレッドシート抽出ロジック ---
def time_schedule_from_drive(sheets_service, file_id):
    """スプレッドシートから拠点ごとのデータを読み込み"""
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
    """
    A-C列 + 時間列を抽出。
    - B列は常に文字列（変換なし）
    - 時間変換は勤務地行（0行目）のみ適用
    - 1行目以降は数値であっても変換せずそのまま
    """
    if loc_df.empty: return loc_df

    key_row = loc_df.iloc[0, :].tolist()
    col_start, col_end = None, len(key_row)

    # 勤務地行のD列(3)以降で、最初に数値がヒットする列を特定
    for c in range(3, len(key_row)):
        if re.match(r'^\d+(\.\d+)?$', str(key_row[c]).strip()):
            col_start = c
            break

    if col_start is None: return loc_df.iloc[:, 0:3]

    # 数値が途切れ、文字列が現れるまでを時間範囲とする
    for c in range(col_start, len(key_row)):
        val_str = str(key_row[c]).strip()
        if val_str != "" and not re.match(r'^\d+(\.\d+)?$', val_str):
            col_end = c
            break

    base_info = loc_df.iloc[:, 0:3].copy() # A, B, C列
    time_data = loc_df.iloc[:, col_start:col_end].copy() # 時間データ列

    # 時間列の処理：勤務地行のみ変換を適用
    for col in time_data.columns:
        # 0行目（勤務地行）の見出しを時刻変換
        val_top = time_data.iloc[0].loc[col]
        time_data.iloc[0, time_data.columns.get_loc(col)] = convert_num_to_time_str(val_top)
        
        # 1行目（スタッフ行など）以降は変換せず、そのままの値を維持
        if len(time_data) > 1:
            time_data.iloc[1:, time_data.columns.get_loc(col)] = \
                time_data.iloc[1:, time_data.columns.get_loc(col)].astype(str)

    return pd.concat([base_info, time_data], axis=1)

# --- 4. PDF解析ロジック ---
def get_key_and_schedule(pdf_stream, time_dic):
    """PDFの0列目を検索してKeyを特定"""
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
    try:
        tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice')
        if not tables: return None
        
        df = tables[0].df
        matched_key, raw_val = None, None

        # PDFの0列目を上から順に走査
        for val in df.iloc[:, 0]:
            # 不要な文字（日付や記号）を除去してKey候補を抽出
            clean_val = normalize_text(re.sub(r'[\d/:()月火水木金土日]', '', str(val)))
            if not clean_val: continue
            
            # マスターのKeyと照合
            found_key = next((k for k in time_dic.keys() if clean_val in k or k in clean_val), None)
            if found_key:
                matched_key = found_key
                raw_val = val
                break
        
        if matched_key:
            return {'key': matched_key, 'time_schedule': time_dic[matched_key], 'raw': raw_val}
    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")
    return None
