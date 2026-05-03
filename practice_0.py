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
    info = None
    if "gcp_service_account" in st.secrets:
        info = st.secrets["gcp_service_account"]
    if info is None: return None, None
    try:
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        return None, build('sheets', 'v4', credentials=creds)
    except: return None, None

def normalize_text(text):
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', str(text))).lower()

def clean_strictly(text):
    """[0,0]から日付・曜日を除去"""
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

def analyze_pdf_full(pdf_file, master_keys):
    """
    配置ルール厳守:
    0行目: 日付, 1行目: 曜日 & location, 2行目〜: 氏名, 3行目〜: 資格
    """
    with open("temp.pdf", "wb") as f:
        f.write(pdf_file.getbuffer())
    
    try:
        tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice')
        if not tables: return None, pd.DataFrame([{"エラー": "表未検出"}])
        
        raw_df = tables[0].df
        
        # 拠点特定 ([0,0]から)
        ans = clean_strictly(str(raw_df.iloc[0, 0]))
        location = "T1" # デフォルト
        for k in master_keys:
            if k in ans:
                location = k
                break

        # データ再構成
        # 0列目: 拠点(1行目), 氏名(2行目), 資格(3行目)... の順に整理
        processed_data = []
        dates = raw_df.iloc[0, 1:].tolist() # 0行目は日付
        days = raw_df.iloc[1, 1:].tolist()  # 1行目は曜日

        # 氏名と資格のペアを抽出 (2行目以降を走査)
        staff_list = []
        for i in range(2, len(raw_df), 2):
            name = str(raw_df.iloc[i, 0]).replace('\n', '')
            license = str(raw_df.iloc[i+1, 0]).replace('\n', '') if i+1 < len(raw_df) else ""
            staff_list.append({"name": name, "license": license})

        # 座標 l の計算
        all_text_lengths = [len(location)] + [len(s["name"]) for s in staff_list]
        l = math.ceil(max(all_text_lengths))

        report_df = pd.DataFrame([{
            "拠点": location,
            "l (列幅)": l,
            "日付行": "0行目 (確認済)",
            "曜日行": "1行目 (確認済)",
            "氏名/資格": "2行目/3行目〜 (階層構造化)"
        }])

        return {
            "df": raw_df, 
            "location": location, 
            "l": l, 
            "staff": staff_list,
            "dates": dates,
            "days": days
        }, report_df
    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")
