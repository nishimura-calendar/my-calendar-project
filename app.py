import streamlit as st
import pandas as pd
import unicodedata
from google.oauth2 import service_account
from googleapiclient.discovery import build
from practice_0 import pdf_reader, extract_year_month, time_schedule_from_drive, data_integration

def format_time(val):
    try:
        num = float(val)
        h = int(num * 24 if num < 1 else num)
        m = int(round((num * 24 - h) * 60 if num < 1 else (num - h) * 60))
        return f"{h:02d}:{m:02d}"
    except: return str(val)

def shift_cal(key, target_date, col, shift_info, other_staff_shift, t_s, final_rows):
    """場所ごとの時程表(t_s)を用いて勤務時間を抽出"""
    valid_locations = t_s.iloc[:, 0].astype(str).unique().tolist()
    time_headers = [format_time(t_s.iloc[0, c]) for c in range(t_s.shape[1])]
    
    clean_info = unicodedata.normalize('NFKC', str(shift_info)).strip()
    my_row = t_s[t_s.iloc[:, 1] == clean_info]
    if my_row.empty: return

    final_rows.append([f"{key}_{clean_info}", target_date, "", target_date, "", "True", "", key])
    
    prev_val = ""
    for t_col in range(2, t_s.shape[1]):
        current_val = str(my_row.iloc[0, t_col]).strip()
        is_work = current_val in valid_locations and current_val not in ["出勤", "退勤", "実働", "休憩"]
        actual_val = current_val if is_work else ""

        if actual_val != prev_val:
            if actual_val != "":
                if prev_val != "" and len(final_rows) > 0 and final_rows[-1][5] == "False":
                    final_rows[-1][4] = time_headers[t_col]
                final_rows.append([f"({prev_val})=>【{actual_val}】", target_date, time_headers[t_col], target_date, "", "False", "", key])
            else:
                if len(final_rows) > 0 and final_rows[-1][5] == "False":
                    final_rows[-1][4] = time_headers[t_col]
            prev_val = actual_val

# --- Streamlit メイン ---
st.title("📅 シフト一括変換 (複数勤務地・本町対応)")
up = st.file_uploader("PDFを選択", type="pdf")

if up and st.button("変換開始"):
    info = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(info, scopes=['https://www.googleapis.com/auth/drive.readonly'])
    service = build('drive', 'v3', credentials=creds)
    
    time_sched_dic = time_schedule_from_drive(service, "1p7EBN1zTTt09etuQkZTIXBlNutUZqQkG")
    y, m = extract_year_month(up)
    pdf_dic = pdf_reader(up, "西村文宏")
    integrated = data_integration(pdf_dic, time_sched_dic)
    
    for loc_key, data in integrated.items():
        my_s, other_s, t_s = data[0], data[1], data[2]
        res = []
        for col in range(1, my_s.shape[1]):
            v1 = str(my_s.iloc[0, col]).strip() # 名前/本町行
            v2 = str(my_s.iloc[1, col]).strip() # 記号行
            
            # 【重要】本町なら2行目を採用
            target_shift = v2 if "本町" in v1 else v1
            if not target_shift or target_shift.lower() == "nan": continue
            
            dt = f"{y}/{m}/{col}"
            if any(h in target_shift for h in ["休", "有給", "公休"]):
                res.append([f"{loc_key}_休日", dt, "", dt, "", "True", "", loc_key])
            else:
                shift_cal(loc_key, dt, col, target_shift, other_s, t_s, res)
        
        if res:
            st.subheader(f"📍 {loc_key}")
            df_out = pd.DataFrame(res, columns=['Subject','Start Date','Start Time','End Date','End Time','All Day Event','Description','Location'])
            st.dataframe(df_out)
            st.download_button(f"{loc_key}のCSV保存", df_out.to_csv(index=False, encoding='utf-8-sig'), f"shift_{loc_key}.csv")
