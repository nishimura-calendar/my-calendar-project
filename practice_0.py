import streamlit as st
import pandas as pd
import re
import unicodedata
import camelot
import os
import math
import calendar
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

# --- 時程表読込・数値変換 (source: 7) ---
def load_time_schedule(sheets_service, file_id):
    spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=file_id).execute()
    time_dic = {}
    for s in spreadsheet.get('sheets', []):
        title = s.get("properties", {}).get("title")
        res = sheets_service.spreadsheets().values().get(spreadsheetId=file_id, range=f"'{title}'!A1:Z300").execute()
        vals = res.get('values', [])
        if not vals: continue
        df = pd.DataFrame(vals).fillna('')
        current_loc, start_idx = None, 0
        for i in range(len(df)):
            val_a = str(df.iloc[i, 0]).strip()
            if val_a != "":
                if current_loc:
                    time_dic[normalize_text(current_loc)] = process_schedule_block(df.iloc[start_idx:i, :])
                current_loc, start_idx = val_a, i
        if current_loc:
            time_dic[normalize_text(current_loc)] = process_schedule_block(df.iloc[start_idx:, :])
    return time_dic
    
def process_schedule_block(block_df):
    def num_to_time(val):
        try:
            # 入力が数値（または数値文字列）の場合のみ変換を試みる
            f_val = float(val)
            hours = int(f_val)
            minutes = int(round((f_val - hours) * 60))
            return f"{hours:02d}:{minutes:02d}"
        except (ValueError, TypeError):
            # 変換できない場合（すでに文字列など）はそのまま返す
            return val

    # A〜C列を保持
    new_df = block_df.iloc[:, :3].copy()
    # D列以降（時間データ）に対して一括処理
    # Pandas 2.1+ に対応するため applymap ではなく map を使用
    time_cols = block_df.iloc[:, 3:].map(num_to_time) 
    
    return pd.concat([new_df, time_cols], axis=1)
    
# --- 第一関門: 日付・曜日の整合性 (source: 9) ---
def verify_first_gate(filename, pdf_0_0, manual_date=None):
    if manual_date:
        y, m = manual_date
    else:
        match = re.search(r'(\d{4})[年\-_](\d{1,2})', filename)
        if not match: return False, "年月抽出失敗", None
        y, m = int(match.group(1)), int(match.group(2))
    
    _, last_day_calc = calendar.monthrange(y, m)
    w_list = ["月", "火", "水", "木", "金", "土", "日"]
    first_w_calc = w_list[calendar.weekday(y, m, 1)]

    found_dates = [int(d) for d in re.findall(r'\b([1-9]|[12][0-9]|3[01])\b', pdf_0_0)]
    found_days = re.findall(r'[月火水木金土日]', pdf_0_0)
    
    last_day_pdf = max(found_dates) if found_dates else 0
    first_w_pdf = found_days[0] if found_days else ""

    if last_day_calc == last_day_pdf and first_w_calc == first_w_pdf:
        return True, "通過", (found_dates, found_days)
    return False, f"不一致: 期待{last_day_calc}日/{first_w_calc}, PDF{last_day_pdf}日/{first_w_pdf}", None

# --- PDF構造化 (source: 9) ---
def analyze_pdf_structural(pdf_stream, master_keys, filename, manual_date=None):
    with open("temp.pdf", "wb") as f: f.write(pdf_stream.getbuffer())
    try:
        tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice')
        if not tables: return None, "表未検出"
        raw_df = tables[0].df
        
        raw_0_0 = str(raw_df.iloc[0, 0])
        success, msg, date_info = verify_first_gate(filename, raw_0_0, manual_date)
        if not success: return None, msg

        found_dates, found_days = date_info
        location = "T1"
        for k in master_keys:
            if k in normalize_text(raw_0_0):
                location = k
                break
        
        # 座標 l の算出 (source: 9)
        names_only = [str(raw_df.iloc[i, 0]).split('\n')[0] for i in range(2, len(raw_df)) if i % 2 == 0]
        l = math.ceil(max([len(n) for n in names_only] + [len(location)]))
        
        # [0,0]空欄化、[1,0]拠点配置 (source: 9)
        final_rows = [[""] + found_dates, [location] + found_days]
        staff_list = []

        for i in range(2, len(raw_df)):
            cell = str(raw_df.iloc[i, 0]).strip()
            row_data = raw_df.iloc[i, 1:].tolist()
            if i % 2 == 0: # 氏名行
                name = cell.split('\n')[0]
                staff_list.append(name)
                final_rows.append([name] + row_data)
            else: # 資格行
                final_rows.append([cell] + row_data)

        return {"df": pd.DataFrame(final_rows), "location": location, "l": l, "staff_list": staff_list}, "通過"
    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")
