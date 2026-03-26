import streamlit as st
import pandas as pd
import unicodedata
import re
from googleapiclient.discovery import build
from google.oauth2 import service_account
from practice_0 import pdf_reader, extract_year_month, time_schedule_from_drive

EXCLUDE_WORDS = ["出勤", "退勤", "実働", "休憩", "深夜", "残業", "施設"]

def format_time(val):
    try:
        num = float(val)
        if num < 1: 
            h = int(num * 24); m = int(round((num * 24 - h) * 60))
        else: 
            h = int(num); m = int(round((num - h) * 60))
        return f"{h:02d}:{m:02d}"
    except: return str(val)

def is_work_value(val):
    s = str(val).strip()
    if s == "" or s.lower() == "nan" or re.fullmatch(r'\d+(\.\d+)?', s): return False
    if any(w in s for w in EXCLUDE_WORDS): return False
    return True

def shift_cal(key, target_date, col, shift_info, other_staff_shift, t_s, final_rows):
    clean_info = unicodedata.normalize('NFKC', str(shift_info)).strip()
    my_row = t_s[t_s.iloc[:, 1] == clean_info]
    if my_row.empty: return

    time_headers = [format_time(t_s.iloc[0, c]) for c in range(t_s.shape[1])]
    final_rows.append([f"{key}_{clean_info}", target_date, "", target_date, "", "True", "", key])
    
    prev_val = "" 
    for t_col in range(2, t_s.shape[1]):
        current_val = str(my_row.iloc[0, t_col]).strip()
        actual_val = current_val if is_work_value(current_val) else ""

        if actual_val != prev_val:
            if actual_val != "": 
                # 【変化点10：開始】
                handing_over_dep = f"({prev_val})" if prev_val != "" else ("(交代)" if (t_s.iloc[:, t_col] == "" and t_s.iloc[:, t_col-1] != "").any() else "")
                if prev_val != "" and len(final_rows) > 0 and final_rows[-1][5] == "False":
                    final_rows[-1][4] = time_headers[t_col]
                
                # to/from抽出 (省略)
                subject = f"{handing_over_dep}=>【{actual_val}】" 
                final_rows.append([subject, target_date, time_headers[t_col], target_date, "", "False", "", key])
            else:
                # 【変化点9：終了】
                if len(final_rows) > 0 and final_rows[-1][5] == "False":
                    final_rows[-1][4] = time_headers[t_col]
            prev_val = actual_val

# --- メイン処理 ---
st.title("📅 西村様専用 シフト変換")
up = st.file_uploader("PDFアップロード", type="pdf")

if up and st.button("変換"):
    info = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(info, scopes=['https://www.googleapis.com/auth/drive.readonly'])
    service = build('drive', 'v3', credentials=creds)
    loc_dic = time_schedule_from_drive(service, "1p7EBN1zTTt09etuQkZTIXBlNutUZqQkG")
    y, m = extract_year_month(up)
    my_s, other_s = pdf_reader(up, "西村文宏")
    
    res = []
    for col in range(1, my_s.shape[1]):
        # --- 本町対応ロジック ---
        val_1 = str(my_s.iloc[0, col]).strip() # 1行目
        val_2 = str(my_s.iloc[1, col]).strip() # 2行目
        
        # 1行目が「本町」なら2行目の記号を採用。そうでなければ1行目を採用
        target_shift = val_2 if "本町" in val_1 else val_1
        
        if not target_shift or "nan" in target_shift.lower(): continue
        dt = f"{y}/{m}/{col}"
        
        if any(h in target_shift for h in ["休", "有給", "公休"]):
            res.append(["T2_休日", dt, "", dt, "", "True", "", "T2"])
        elif "T2" in loc_dic:
            shift_cal("T2", dt, col, target_shift, other_s, loc_dic["T2"], res)
            
    if res:
        df = pd.DataFrame(res, columns=['Subject','Start Date','Start Time','End Date','End Time','All Day Event','Description','Location'])
        st.table(df)
        st.download_button(f"{y}年{m}月のCSV保存", df.to_csv(index=False, encoding='utf-8-sig'), f"shift_{y}_{m}.csv")
