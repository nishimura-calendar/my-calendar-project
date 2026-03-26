import streamlit as st
import pandas as pd
import unicodedata
from googleapiclient.discovery import build
from google.oauth2 import service_account
from practice_0 import pdf_reader, extract_year_month, time_schedule_from_drive

# 除外設定（勤務場所ではない項目）
EXCLUDE_WORDS = ["出勤", "退勤", "実働", "休憩", "深夜", "残業", "10:00", "20:00"]

def format_time(val):
    """数値やシリアル値を HH:MM 形式に変換"""
    try:
        num = float(val)
        if num < 1: # シリアル値
            h = int(num * 24)
            m = int(round((num * 24 - h) * 60))
        else: # 17.5 などの数値
            h = int(num)
            m = int(round((num - h) * 60))
        return f"{h:02d}:{m:02d}"
    except: return str(val)

def shift_cal(key, target_date, col, shift_info, other_staff_shift, t_s, final_rows):
    """西村さんの変化点ロジック：勤務中のみを抽出し、正確に閉じる"""
    clean_info = unicodedata.normalize('NFKC', str(shift_info)).strip()
    my_row = t_s[t_s.iloc[:, 1] == clean_info]
    if my_row.empty: return

    # 時刻ヘッダー（0行目）を事前変換
    time_headers = [format_time(t_s.iloc[0, c]) for c in range(t_s.shape[1])]
    
    # 背景用の終日予定
    final_rows.append([f"{key}_{clean_info}", target_date, "", target_date, "", "True", "", key])
    
    prev_val = "" # 空文字でスタート（変化点検知の鍵）
    for t_col in range(2, t_s.shape[1]):
        current_val = str(my_row.iloc[0, t_col]).strip()
        # 勤務場所かどうかの判定
        is_work = current_val != "" and not any(w in current_val for w in EXCLUDE_WORDS)
        actual_val = current_val if is_work else ""

        if actual_val != prev_val:
            if actual_val != "": 
                # --- 【開始・移動：行の新規作成】 ---
                handing_over_dep = ""
                mask_handing_over = pd.Series([False] * len(t_s))
                
                if prev_val == "": 
                    # 勤務開始（交代確認）
                    mask_handing_over = (t_s.iloc[:, t_col] == "") & (t_s.iloc[:, t_col-1] != "")
                    if mask_handing_over.any(): handing_over_dep = "(交代)"
                else:
                    # 部署移動（前の行を閉じてから、今の部署名を冠する）
                    if len(final_rows) > 0 and final_rows[-1][5] == "False":
                        final_rows[-1][4] = time_headers[t_col]
                    handing_over_dep = f"({prev_val})" 
                    mask_handing_over = (t_s.iloc[:, t_col] == prev_val)
                
                mask_taking_over = (t_s.iloc[:, t_col-1] == actual_val)   
                
                # to/from の名前抽出
                names = ["", ""]
                for i, mask in enumerate([mask_handing_over, mask_taking_over]):
                    keys = t_s.loc[mask, t_s.columns[1]]
                    targets = other_staff_shift[other_staff_shift.iloc[:, col].isin(keys)]
                    name_list = targets.iloc[:, 0].unique().astype(str)
                    if len(name_list) > 0:
                        prefix = "to " if i == 0 else "from "
                        names[i] = f"{prefix}{'・'.join(name_list)}"
                
                subject = f"{handing_over_dep}{names[0]}=>【{actual_val}】{names[1]}"
                final_rows.append([subject, target_date, time_headers[t_col], target_date, "", "False", "", key])
            
            else:
                # --- 【終了・休憩：行を閉じるだけ】 ---
                if len(final_rows) > 0 and final_rows[-1][5] == "False":
                    final_rows[-1][4] = time_headers[t_col]
            
            prev_val = actual_val

# --- UI ---
st.set_page_config(page_title="シフト変換", layout="wide")
st.title("📅 シフトカレンダー一括変換（最適版）")

up = st.file_uploader("PDFをアップロード", type="pdf")
if up and st.button("変換実行"):
    # Google API認証
    info = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(info, scopes=['https://www.googleapis.com/auth/drive.readonly'])
    service = build('drive', 'v3', credentials=creds)
    
    loc_dic = time_schedule_from_drive(service, "1p7EBN1zTTt09etuQkZTIXBlNutUZqQkG")
    y, m = extract_year_month(up)
    my_s, other_s = pdf_reader(up, "西村文宏")
    
    res = []
    for col in range(1, my_s.shape[1]):
        code = str(my_s.iloc[0, col]).strip()
        if not code or "nan" in code.lower(): continue
        dt = f"{y}/{m}/{col}"
        
        if any(h in code for h in ["休", "有給", "公休"]):
            res.append(["T2_休日", dt, "", dt, "", "True", "", "T2"])
        elif "T2" in loc_dic:
            shift_cal("T2", dt, col, code, other_s, loc_dic["T2"], res)
            
    if res:
        df = pd.DataFrame(res, columns=['Subject','Start Date','Start Time','End Date','End Time','All Day Event','Description','Location'])
        st.table(df)
        csv = df.to_csv(index=False, encoding='utf-8-sig')
        st.download_button("CSVを保存", csv, f"shift_{y}_{m}.csv", "text/csv")
