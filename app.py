import streamlit as st
import pandas as pd
import unicodedata
from google.oauth2 import service_account
from googleapiclient.discovery import build
from web_practice_0 import (
    pdf_reader, extract_year_month, time_schedule_from_drive, 
    data_integration, parse_special_shift
)

def format_time(val):
    try:
        num = float(val)
        h = int(num * 24 if num < 1 else num)
        m = int(round((num * 24 - h) * 60 if num < 1 else (num - h) * 60))
        return f"{h:02d}:{m:02d}"
    except: return str(val)

def shift_cal(loc_name, target_date, day_col, shift_info, other_s, t_s, final_rows):
    """詳細な変化点と交代相手を算出"""
    valid_locs = t_s.iloc[:, 0].astype(str).unique().tolist()
    time_headers = [format_time(t_s.iloc[0, c]) for c in range(t_s.shape[1])]
    clean_info = unicodedata.normalize('NFKC', str(shift_info)).strip()
    my_time_row = t_s[t_s.iloc[:, 1] == clean_info]
    if my_time_row.empty: return

    # 背景イベント
    final_rows.append([f"{loc_name}_{clean_info}", target_date, "", target_date, "", "True", "", loc_name])
    
    prev_val = ""
    for t_col in range(2, t_s.shape[1]):
        current_val = str(my_time_row.iloc[0, t_col]).strip()
        actual_val = current_val if (current_val in valid_locs and current_val not in ["出勤","退勤","実働","休憩"]) else ""

        if actual_val != prev_val:
            if len(final_rows) > 0 and final_rows[-1][5] == "False":
                final_rows[-1][4] = time_headers[t_col]
            
            if actual_val != "":
                # 交代相手の検索（同じ列に同じ記号を持つ人）
                partners = []
                for r_idx in range(len(other_s)):
                    cell_val = str(other_s.iloc[r_idx, day_col])
                    if clean_info in cell_val and other_s.iloc[r_idx, 0] != "西村文宏":
                        partners.append(other_s.iloc[r_idx, 0])
                partner_name = " / ".join(partners) if partners else ""
                
                prefix = f"(交代)to {partner_name}" if partner_name else ""
                subj = f"{prefix}=>【{actual_val}】" if prev_val == "" else f"({prev_val})=>【{actual_val}】"
                final_rows.append([subj, target_date, time_headers[t_col], target_date, "", "False", "", loc_name])
            prev_val = actual_val

# --- Streamlit ---
st.title("📅 シフト一括変換（本町・複数勤務地 完全対応版）")
up = st.file_uploader("シフトPDFをアップロード", type="pdf")

if up and st.button("変換開始"):
    info = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(info, scopes=['https://www.googleapis.com/auth/drive.readonly'])
    service = build('drive', 'v3', credentials=creds)
    
    t_dic = time_schedule_from_drive(service, "1p7EBN1zTTt09etuQkZTIXBlNutUZqQkG")
    y, m = extract_year_month(up)
    p_dic = pdf_reader(up, "西村文宏")
    integrated = data_integration(p_dic, t_dic)
    
    for loc_key, data in integrated.items():
        my_s, other_s, t_s = data[0], data[1], data[2]
        res = []
        for col in range(1, my_s.shape[1]):
            v1 = str(my_s.iloc[0, col]).strip() # 名前/本町
            v2 = str(my_s.iloc[1, col]).strip() # 記号/9@14
            dt = f"{y}/{m}/{col}"
            
            # --- 1. 特殊シフト（@あり）の判定 ---
            s_t, e_t, is_spec = parse_special_shift(v2)
            if is_spec:
                res.append([f"{v1}_{v2}", dt, s_t, dt, e_t, "False", "", loc_key])
                continue
            
            # --- 2. 通常の記号処理 ---
            target_shift = v1 if v1 and "nan" not in v1.lower() else ""
            if not target_shift: continue
            
            if any(h in target_shift for h in ["休", "有給", "公休"]):
                res.append([f"{loc_key}_休日", dt, "", dt, "", "True", "", loc_key])
            else:
                shift_cal(loc_key, dt, col, target_shift, other_s, t_s, res)
        
        if res:
            st.subheader(f"📍 {loc_key}")
            df_out = pd.DataFrame(res, columns=['Subject','Start Date','Start Time','End Date','End Time','All Day Event','Description','Location'])
            st.dataframe(df_out)
            st.download_button(f"{loc_key}のCSVを保存", df_out.to_csv(index=False, encoding='utf-8-sig'), f"shift_{loc_key}.csv")
