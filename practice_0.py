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
    info = st.secrets.get("gcp_service_account")
    if not info: return None, None
    try:
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        return build('drive', 'v3', credentials=creds), build('sheets', 'v4', credentials=creds)
    except: return None, None

def normalize_text(text):
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', str(text))).lower()

def clean_strictly(text):
    """[0,0]から拠点Keyのみを抽出"""
    text = re.sub(r'\b([1-9]|[12][0-9]|3[01])\b', '', str(text))
    text = re.sub(r'[月火水木金土日()/:：\s　\n]', '', text)
    return normalize_text(text)

def convert_num_to_time_str(val):
    try:
        num = float(str(val).strip())
        hours = int(num)
        minutes = int(round((num - hours) * 60))
        return f"{hours:02d}:{minutes:02d}"
    except: return str(val)

# --- 2. 時程表の読み込み ---
def time_schedule_from_drive(sheets_service, file_id):
    spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=file_id).execute()
    location_data_dic = {}
    for s in spreadsheet.get('sheets', []):
        title = s.get("properties", {}).get("title")
        res = sheets_service.spreadsheets().values().get(spreadsheetId=file_id, range=f"'{title}'!A1:Z200").execute()
        vals = res.get('values', [])
        if not vals: continue
        df = pd.DataFrame(vals).fillna('')
        current_key, start_row = None, 0
        for i in range(len(df)):
            val_a = str(df.iloc[i, 0]).strip()
            if val_a != "":
                if current_key:
                    sub_df = df.iloc[start_row:i, :].copy()
                    for c in range(3, len(sub_df.columns)):
                        sub_df.iloc[0, c] = convert_num_to_time_str(sub_df.iloc[0, c])
                    location_data_dic[normalize_text(current_key)] = sub_df
                current_key, start_row = val_a, i
        if current_key:
            sub_df = df.iloc[start_row:, :].copy()
            for c in range(3, len(sub_df.columns)):
                sub_df.iloc[0, c] = convert_num_to_time_str(sub_df.iloc[0, c])
            location_data_dic[normalize_text(current_key)] = sub_df
    return location_data_dic

# --- 3. PDF解析 (配置ルール厳守) ---
def analyze_pdf_full(pdf_file, master_keys):
    with open("temp.pdf", "wb") as f:
        f.write(pdf_file.getbuffer())
    try:
        tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice')
        if not tables: return None, pd.DataFrame([{"エラー": "表未検出"}])
        
        raw_df = tables[0].df
        
        # 1. 拠点特定 ([0,0]解析)
        ans = clean_strictly(str(raw_df.iloc[0, 0]))
        location = "T1"
        for k in master_keys:
            if k in ans:
                location = k
                break

        # 2. ヘッダーの分離
        # 0行目: 日付, 1行目: 曜日
        dates = raw_df.iloc[0, 1:].values.tolist()
        days = raw_df.iloc[1, 1:].values.tolist()

        # 3. 2行目以降の氏名・資格の抽出
        # 氏名行(2, 4, 6...)と資格行(3, 5, 7...)をセットで処理
        structured_staff_data = []
        for i in range(2, len(raw_df), 2):
            # 氏名データ (i行目)
            name_row = raw_df.iloc[i, :].tolist()
            # 資格データ (i+1行目)
            license_row = raw_df.iloc[i+1, :].tolist() if i+1 < len(raw_df) else [""] * len(name_row)
            
            structured_staff_data.append({
                "name_row": name_row,
                "license_row": license_row
            })

        # 4. 表示用データフレームの作成 (要求された配置を再現)
        # 行0: [NaN, 日付...]
        # 行1: [拠点, 曜日...]
        # 行2: [氏名, シフト...]
        # 行3: [資格, 補助データ...]
        
        rows = []
        rows.append(["0: 日付"] + dates)
        rows.append(["1: 曜日 (" + location + ")"] + days)
        
        max_name_len = len(location)
        for staff in structured_staff_data:
            rows.append(staff["name_row"])
            rows.append(staff["license_row"])
            # 座標 l の計算用
            name_str = str(staff["name_row"][0]).split('\n')[0]
            max_name_len = max(max_name_len, len(name_str))

        final_df = pd.DataFrame(rows)
        l = math.ceil(max_name_len)

        report_df = pd.DataFrame([{
            "拠点": location,
            "算出座標 l": l,
            "構造判定": "日付(0行) / 曜日(1行) / 氏名・資格(2行以降)"
        }])

        return {"df": final_df, "location": location, "l": l}, report_df
    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")
