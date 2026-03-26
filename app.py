import streamlit as st
import pandas as pd
import unicodedata
import re
from google.oauth2 import service_account
from googleapiclient.discovery import build
from practice_0 import (
    pdf_reader, extract_year_month, time_schedule_from_drive, 
    data_integration, parse_special_shift
)

def format_time(val):
    """Excelの数値/シリアル値を時刻(HH:MM)に変換"""
    try:
        num = float(val)
        h = int(num * 24 if num < 1 else num)
        m = int(round((num * 24 - h) * 60 if num < 1 else (num - h) * 60))
        return f"{h:02d}:{m:02d}"
    except:
        return str(val)

def shift_cal(loc_name, target_date, day_col, shift_info, other_s, t_s, final_rows):
    """
    西村さんのエクセル資料「変化点9・10」を完全再現したロジック。
    引受け元(handing_over)と引受け先(taking_over)をSubjectに反映します。
    """
    time_headers = [format_time(t_s.iloc[0, c]) for c in range(t_s.shape[1])]
    clean_info = unicodedata.normalize('NFKC', str(shift_info)).strip()
    
    my_time_row = t_s[t_s.iloc[:, 1].astype(str).str.strip() == clean_info]
    if my_time_row.empty:
        return

    # 1. 終日イベント（背景情報）
    final_rows.append([f"{loc_name}_{clean_info}", target_date, "", target_date, "", "True", "", loc_name])
    
    # 2. 相手（人）の特定：同じ日の同じシフト記号を持つ自分以外のスタッフ
    opponents = []
    for r_idx in range(len(other_s)):
        cell_val = unicodedata.normalize('NFKC', str(other_s.iloc[r_idx, day_col])).strip()
        staff_name = str(other_s.iloc[r_idx, 0]).replace('\n', '').strip()
        if clean_info == cell_val and "西村" not in staff_name and staff_name != "":
            opponents.append(staff_name)
    
    # 引受・引渡しの「人」のコンテキスト
    person_context = " / ".join(list(set(opponents))) if opponents else "担当"

    # 3. 業務変化点の処理（エクセル資料のロジック）
    prev_val = ""
    last_event_idx = -1
    
    for t_col in range(2, t_s.shape[1]):
        val = str(my_time_row.iloc[0, t_col]).strip()
        # 有効な場所・業務名のみ抽出
        actual_val = val if val not in ["出勤","退勤","実働時間","休憩時間","深夜","nan","","0","0.0"] else ""

        if actual_val != prev_val:
            # --- 変化点 9：直前のイベントの終了時刻を確定 ---
            if len(final_rows) > 0 and final_rows[-1][4] == "" and final_rows[-1][5] == "False":
                final_rows[-1][4] = time_headers[t_col]
            
            # --- 変化点 10：新規Subjectの作成 ---
            if actual_val != "":
                # エクセルの subject={handing_over} => {taking_over} の再現
                if prev_val == "":
                    # 勤務開始時：人(handing_over) から 場所(taking_over) へ
                    handing_over = person_context
                    taking_over = f"【{actual_val}】"
                else:
                    # 業務交代時：場所(handing_over) から 場所(taking_over) へ
                    handing_over = prev_val
                    taking_over = f"【{actual_val}】"
                
                subj = f"({handing_over}) => {taking_over}"
                final_rows.append([subj, target_date, time_headers[t_col], target_date, "", "False", "", loc_name])
                last_event_idx = len(final_rows) - 1 # 最後の業務位置を更新
            
            prev_val = actual_val

    # 4. 勤務終了の処理（引渡し）
    # 最後に登録された業務イベントに、人への引渡しを追記
    if last_event_idx != -1:
        current_subj = final_rows[last_event_idx][0]
        # (最後の場所) => 引渡(人) を追加
        final_rows[last_event_idx][0] = f"{current_subj} => 引渡({person_context})"

# --- Streamlit インターフェース ---
st.set_page_config(page_title="シフト変換ツール（完全版）", layout="wide")
st.title("📅 シフト一括変換システム")
st.write("西村さん専用：人・場所の引受け・引渡し対応版")

up = st.file_uploader("勤務予定表(PDF)をアップロードしてください", type="pdf")

if up and st.button("変換を実行"):
    if "gcp_service_account" not in st.secrets:
        st.error("Secretsに 'gcp_service_account' が設定されていません。")
    else:
        info = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        service = build('drive', 'v3', credentials=creds)
        
        with st.spinner('解析中...'):
            t_dic = time_schedule_from_drive(service, "1p7EBN1zTTt09etuQkZTIXBlNutUZqQkG")
            y, m = extract_year_month(up)
            p_dic = pdf_reader(up, "西村文宏")
            integrated = data_integration(p_dic, t_dic)
        
        if not integrated:
            st.warning("該当データがありませんでした。")
        
        for loc_key, data in integrated.items():
            my_s, other_s, t_s = data[0], data[1], data[2]
            res = []
            
            for col in range(1, my_s.shape[1]):
                v1 = str(my_s.iloc[0, col]).strip()
                v2 = str(my_s.iloc[1, col]).strip()
                dt = f"{y}/{m}/{col}"
                
                # 特殊対応（本町など @ 判定）
                s_t, e_t, is_spec = parse_special_shift(v2)
                if is_spec:
                    res.append([f"{v1}_{v2}", dt, s_t, dt, e_t, "False", "", loc_key])
                    continue
                
                # 通常対応
                target_shift = v1 if v1 and "nan" not in v1.lower() else ""
                if not target_shift:
                    continue
                
                if any(h in target_shift for h in ["休", "有給", "公休"]):
                    res.append([f"{loc_key}_休日", dt, "", dt, "", "True", "", loc_key])
                else:
                    shift_cal(loc_key, dt, col, target_shift, other_s, t_s, res)
            
            if res:
                st.subheader(f"📍 {loc_key}")
                df_out = pd.DataFrame(res, columns=['Subject','Start Date','Start Time','End Date','End Time','All Day Event','Description','Location'])
                st.dataframe(df_out)
                csv = df_out.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(f"{loc_key}のCSVを保存", csv, f"shift_{loc_key}_{y}{m}.csv", "text/csv")
