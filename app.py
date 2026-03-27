import streamlit as st
import pandas as pd
import unicodedata
from google.oauth2 import service_account
from googleapiclient.discovery import build
from practice_0 import (
    pdf_reader, extract_year_month, time_schedule_from_drive, 
    data_integration, parse_special_shift
)

# ==========================================
# 設定情報
# ==========================================
TIME_TABLE_ID = "1p7EBN1zTTt09etuQkZTIXBlNutUZqQkG"
TARGET_STAFF = "西村文宏"

def format_time(val):
    try:
        num = float(val)
        h = int(num * 24 if num < 1 else num)
        m = int(round((num * 24 - h) * 60 if num < 1 else (num - h) * 60))
        return f"{h:02d}:{m:02d}"
    except:
        return str(val)

def shift_cal(key, target_date, col, shift_info, other_staff_shift, time_schedule, final_rows):
    for loc_key, data in integrated.items():
        my_s, other_s, t_s = data[0], data[1], data[2]
        res = []
            
        # 時程表(t_s)のB列（インデックス1）にある有効な記号一覧
        valid_symbols = t_s.iloc[:, 1].astype(str).str.strip().unique()
            
        for col in range(1, my_s.shape[1]):
            # v1: 1行目 (my_daily_shift(0, col)), v2: 2行目 (my_daily_shift(1, col))
            v1 = str(my_s.iloc[0, col]).strip()
            v2 = str(my_s.iloc[1, col]).strip()
            dt = f"{y}/{m}/{col}"
                
            if not v1 or "nan" in v1.lower():
                continue

            # --- 1. まず、PDFの表記(v1_v2)で「Subject, True」の一行目を必ず作る ---
            pdf_text = f"{v1}_{v2}" if v2 and v2 != "nan" and v2 != "" else v1
            res.append([pdf_text, dt, "", dt, "", "True", "", loc_key])

            # --- 2. 詳細行の追加判定 ---

            # (A) v1に「本町」が含まれる場合：v2から時間を抽出
            if "本町" in v1:
                # practice_0.py の parse_special_shift 関数を呼び出し
                start_t, end_t, is_spec = parse_special_shift(v2)
                if is_spec:
                    # 詳細行：Subjectは「本町」固定、時間は抽出結果をセット
                    res.append(["本町", dt, start_t, dt, end_t, "False", "", loc_key])
            # (B) それ以外で、時程表に記号(v1)がある場合
            elif v1 in valid_symbols:
                sched_clean = time_schedule.fillna("").astype(str)
                my_time_shift = sched_clean[sched_clean.iloc[:, 1] == shift_info]
                if not my_time_shift.empty:
                    prev_val = ""
                    
                    for t_col in range(2, time_schedule.shape[1]):
                        current_val = my_time_shift.iloc[0, t_col].strip()
                        time_label = format_time(time_schedule.iloc[0, t_col])
                        
                        if current_val != prev_val:
                            
                            if current_val != "": 
                                # --- handing_over (引渡し元/to) の判定 ---
                                handing_over_department = ""
                                mask_handing_over = pd.Series([False] * len(time_schedule))
                                
                                if prev_val == "": 
                                    
                                    # 勤務開始：その場所が空で、1コマ前が埋まっている担当者を探す 
                                    mask_handing_over = (sched_clean.iloc[:, t_col] == "") & (sched_clean.iloc[:, t_col-1] != "")
                                    handing_over_department = "(交代)" if mask_handing_over.any() else ""
                                else:
                                    # 業務交代
                                    handing_over_department = f"({prev_val})" 
                                    mask_handing_over = (sched_clean.iloc[:, t_col] == prev_val)
                                    # 前の予定の終了時間をセット
                                    if len(final_rows) > 0 and final_rows[-1][4] == "" and final_rows[-1][5] == "False":
                                        final_rows[-1][4] = time_label
                                # --- taking_over (引受け先/from) の判定 ---
                                mask_taking_over = (sched_clean.iloc[:, t_col-1] == current_val)  
                                
                                handing_over_str = ""
                                taking_over_str = ""
                                
                                # 2段階で名前を抽出 (i=0: 次の担当者to, i=1: 前の担当者from)
                                for i in range(0, 2):
                                    mask = mask_handing_over if i == 0 else mask_taking_over
                                    search_keys = sched_clean.loc[mask, sched_clean.columns[1]].unique()
                                    target_rows = other_staff_shift[other_staff_shift.iloc[:, col].isin(search_keys)]
                                    names = target_rows.iloc[:, 0].str.replace(r'[\s　]', '', regex=True).unique()
                                    # 自分(西村さん)を除外
                                    names = [n for n in names if TARGET_STAFF not in n and n != ""]
                                    staff_names = "・".join(names) if names else ""
                                    
                                    if i == 0:
                                        suffix = f" to {staff_names}" if staff_names else ""
                                        handing_over_str = f"{handing_over_department}{suffix}"
                                    else:
                                        suffix = f" from {staff_names}" if staff_names else ""
                                        taking_over_str = f"【{current_val}】{suffix}"    
                    
                                final_rows.append([f"{handing_over_str}=>{taking_over_str}", target_date, time_label, target_date, "", "False", "", key])
                            else:
                                # 休憩入りなどの終了時刻確定
                                if len(final_rows) > 0 and final_rows[-1][4] == "" and final_rows[-1][5] == "False":
                                    final_rows[-1][4] = time_label    
                        prev_val = current_val

# --- Streamlit インターフェース ---
st.set_page_config(page_title="シフト変換ツール", layout="wide")
st.title("📅 シフト一括変換システム")
st.write(f"対象者: **{TARGET_STAFF}**")

up = st.file_uploader("勤務予定表(PDF)をアップロード", type="pdf")

if up and st.button("変換を実行"):
    if "gcp_service_account" not in st.secrets:
        st.error("Secrets設定が必要です。")
    else:
        info = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(info, scopes=['https://www.googleapis.com/auth/drive.readonly'])
        service = build('drive', 'v3', credentials=creds)
        
        with st.spinner('解析中...'):
            t_dic = time_schedule_from_drive(service, TIME_TABLE_ID)
            y, m = extract_year_month(up)
            p_dic = pdf_reader(up, TARGET_STAFF)
            integrated = data_integration(p_dic, t_dic)
        
        # --- 表示ループの修正 ---
        for loc_key, data in integrated.items():
            my_s, other_s, t_s = data[0], data[1], data[2]
            res = []
            for col in range(1, my_s.shape[1]):
                v1 = str(my_s.iloc[0, col]).strip()
                v2 = str(my_s.iloc[1, col]).strip()
                dt = f"{y}/{m}/{col}"
                
                # 有給休暇判定：v1, v2のいずれかに文字があれば「休日」扱い
                if any(k in v1 or k in v2 for k in ["有給", "休", "公休", "特休"]):
                    # 明日のために「休日」という言葉を入れて赤色判定させる
                    res.append([f"{loc_key}_休日(有給)", dt, "", dt, "", "True", "", loc_key])
                    continue

                s_t, e_t, is_spec = parse_special_shift(v2)
                if is_spec:
                    # 本町（青）判定用に @ を残す
                    res.append([f"{v1}_{v2}", dt, s_t, dt, e_t, "False", "", loc_key])
                    continue
                
                if v1 and "nan" not in v1.lower():
                    shift_cal(loc_key, dt, col, v1, other_s, t_s, res)
            
            # --- ここが抜けていたため表示されなかった部分 ---
            if res:
                st.subheader(f"📍 {loc_key}")
                df_out = pd.DataFrame(res, columns=['Subject','Start Date','Start Time','End Date','End Time','All Day Event','Description','Location'])
                st.dataframe(df_out) # 画面に表示
                # 保存ボタン
                csv = df_out.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(f"{loc_key}のCSVを保存", csv, f"shift_{loc_key}_{y}{m}.csv", "text/csv")
