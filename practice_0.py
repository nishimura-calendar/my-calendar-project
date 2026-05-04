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

# --- 認証 ---
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

# --- 時程表読込 (source: 7) ---
def load_time_schedule(sheets_service, file_id):
    spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=file_id).execute()
    time_dic = {}
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]

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
    """時程表のD列以降の数字を時間に変換(source: 7)"""
    def num_to_time(val):
        try:
            f_val = float(val)
            hours = int(f_val)
            minutes = int(round((f_val - hours) * 60))
            return f"{hours:02d}:{minutes:02d}"
        except: return val
    
    # 1行目のD列以降から時間列を特定
    header = block_df.iloc[0, 3:].tolist()
    converted_header = [num_to_time(x) for x in header]
    # A-C列 + 変換後の時間列
    new_df = block_df.iloc[:, :3].copy()
    temp_body = block_df.iloc[:, 3:].copy()
    temp_body.columns = converted_header
    return pd.concat([new_df, temp_body], axis=1)

# --- 第一関門: 日付・曜日の整合性 (source: 9) ---
def verify_first_gate(filename, pdf_0_0, manual_date=None):
    if manual_date:
        y, m = manual_date
    else:
        match = re.search(r'(\d{4})[年\-_](\d{1,2})', filename)
        if not match: return False, "年月を抽出できません。手入力してください。", None
        y, m = int(match.group(1)), int(match.group(2))
    
    # ① ファイル名からの算出
    _, last_day_calc = calendar.monthrange(y, m)
    first_w_idx = calendar.weekday(y, m, 1)
    w_list = ["月", "火", "水", "木", "金", "土", "日"]
    first_w_calc = w_list[first_w_idx]

    # ② PDF内容からの抽出 ([0,0]の日付文字列・曜日文字列)
    found_dates = [int(d) for d in re.findall(r'\b([1-9]|[12][0-9]|3[01])\b', pdf_0_0)]
    found_days = re.findall(r'[月火水木金土日]', pdf_0_0)
    
    last_day_pdf = max(found_dates) if found_dates else 0
    first_w_pdf = found_days[0] if found_days else ""

    if last_day_calc == last_day_pdf and first_w_calc == first_w_pdf:
        return True, "通過", (found_dates, found_days)
    else:
        reason = f"不一致: ファイル名({last_day_calc}日/{first_w_calc}) vs PDF({last_day_pdf}日/{first_w_pdf})"
        return False, reason, None

# --- PDF構造化 (source: 9) ---
def analyze_pdf_structural(pdf_stream, master_keys, filename, manual_date=None):
    with open("temp.pdf", "wb") as f: f.write(pdf_stream.getbuffer())
    try:
        tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice')
        if not tables: return None, "表が検出されません"
        raw_df = tables[0].df
        
        # 第一関門チェック
        raw_0_0 = str(raw_df.iloc[0, 0])
        success, msg, date_info = verify_first_gate(filename, raw_0_0, manual_date)
        if not success: return None, msg

        found_dates, found_days = date_info
        
        # location抽出 (source: 9)
        location = "T1"
        clean_text = normalize_text(raw_0_0)
        for k in master_keys:
            if k in clean_text:
                location = k
                break
        
        # 座標設定 (l = 切上値[max(loc長, 氏名最長)]) (source: 9)
        all_names = [str(raw_df.iloc[i, 0]).split('\n')[0] for i in range(2, len(raw_df)) if str(raw_df.iloc[i,0]).strip()]
        max_name_len = max([len(n) for n in all_names] + [len(location)])
        l = math.ceil(max_name_len)
        
        # 構造化
        final_rows = [
            [""] + found_dates,           # 行0: [0,0]は空白 (source: 9)
            [location] + found_days       # 行1: [1,0]はlocation (source: 9)
        ]
        
        staff_list = []
        for i in range(2, len(raw_df)):
            cell = str(raw_df.iloc[i, 0]).strip()
            if not cell or "nan" in cell.lower(): continue
            parts = cell.split('\n')
            name = parts[0]
            staff_list.append(name)
            final_rows.append([name] + raw_df.iloc[i, 1:].tolist()) # 氏名行
            final_rows.append([parts[1] if len(parts)>1 else ""] + [""]*len(found_dates)) # 資格行

        return {
            "df": pd.DataFrame(final_rows),
            "location": location,
            "l": l,
            "staff_list": staff_list
        }, "通過"
    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")
