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

# ... (認証・正規化・時程表読込関数は前回と同様のため省略) ...

def verify_first_gate(filename, pdf_0_0, manual_date=None):
    if manual_date:
        y, m = manual_date
    else:
        # ファイル名から年月抽出 (cite: 9)
        match = re.search(r'(\d{4})[年\-_](\d{1,2})', filename)
        if not match: return False, "年月抽出失敗", None
        y, m = int(match.group(1)), int(match.group(2))
    
    _, last_day_calc = calendar.monthrange(y, m)
    w_list = ["月", "火", "水", "木", "金", "土", "日"]
    first_w_calc = w_list[calendar.weekday(y, m, 1)]

    # PDF [0,0] から情報を抽出 (cite: 9)
    found_dates = [int(d) for d in re.findall(r'\b([1-9]|[12][0-9]|3[01])\b', pdf_0_0)]
    found_days = re.findall(r'[月火水木金土日]', pdf_0_0)
    
    last_day_pdf = max(found_dates) if found_dates else 0
    first_w_pdf = found_days[0] if found_days else ""

    if last_day_calc == last_day_pdf and first_w_calc == first_w_pdf:
        return True, "通過", (found_dates, found_days, y, m)
    return False, f"整合性エラー: 算出={last_day_calc}日 / PDF={last_day_pdf}日", None

def analyze_pdf_structural(pdf_stream, master_keys, filename, manual_date=None):
    with open("temp.pdf", "wb") as f: f.write(pdf_stream.getbuffer())
    try:
        tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice')
        if not tables: return None, "表未検出"
        raw_df = tables[0].df
        raw_0_0 = str(raw_df.iloc[0, 0])
        
        success, msg, date_info = verify_first_gate(filename, raw_0_0, manual_date)
        if not success: return None, msg

        found_dates, found_days, y, m = date_info
        location = "T1"
        for k in master_keys:
            if k in normalize_text(raw_0_0):
                location = k
                break
        
        staff_list = []
        for i in range(2, len(raw_df), 2):
            name = str(raw_df.iloc[i, 0]).split('\n')[0].strip()
            if name and name.lower() != 'nan': staff_list.append(name)

        final_rows = [[""] + found_dates, [location] + found_days]
        for i in range(2, len(raw_df)):
            cell = str(raw_df.iloc[i, 0]).strip()
            row_data = raw_df.iloc[i, 1:].tolist()
            name_val = cell.split('\n')[0] if i % 2 == 0 else cell
            final_rows.append([name_val] + row_data)

        return {
            "df": pd.DataFrame(final_rows),
            "location": location,
            "staff_list": staff_list,
            "year": y, "month": m
        }, "通過"
    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")
