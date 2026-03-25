import streamlit as st
import pandas as pd
import unicodedata
import re
from practice_0 import pdf_reader, extract_year_month, time_schedule_from_drive

def shift_cal(key, target_date, col, shift_info, other_staff_shift, time_schedule, final_rows):
    """Excelの時程表を解析し、場所の移動と引き継ぎ相手を抽出する"""
    # 記号の正規化
    clean_info = unicodedata.normalize('NFKC', str(shift_info)).strip()
    t_s = time_schedule.copy()
    
    # 自分の記号行を特定
    my_row = t_s[t_s.iloc[:, 1] == clean_info]
    if my_row.empty: return

    # 1. 終日イベント（背景）を追加
    final_rows.append([f"{key}_{clean_info}", target_date, "", target_date, "", "True", "", key])
    
    prev_val = ""
    # 時刻列（2列目以降）をスキャン
    for t_col in range(2, t_s.shape[1]):
        raw_val = my_row.iloc[0, t_col]
        current_val = str(raw_val).strip() if pd.notna(raw_val) and str(raw_val).lower() != "nan" else ""
        
        # 場所が変わったか、勤務が終了したタイミング
        if current_val != prev_val:
            # 勤務継続中の場合、前の予定の「終了時刻」をセット
            if len(final_rows) > 0 and final_rows[-1][5] == "False":
                final_rows[-1][4] = str(t_s.iloc[0, t_col]).strip()

            if current_val != "":
                # --- 引き継ぎ情報の構築 ---
                h_dep = ""
                mask_h = pd.Series([False] * len(t_s))
                
                if prev_val == "":
                    # 勤務開始時：交代（直前まで誰かいたか）を確認
                    mask_h = (t_s.iloc[:, t_col].astype(str).replace('nan','') == "") & \
                             (t_s.iloc[:, t_col-1].astype(str).replace('nan','') != "")
                    if mask_h.any(): h_dep = "(交代)"
                else:
                    # 移動時
                    h_dep = f"({prev_val})"
                    mask_h = (t_s.iloc[:, t_col].astype(str).str.strip() == prev_val)

                # 受ける側：直前までその場所にいた人
                mask_t = (t_s.iloc[:, t_col-1].astype(str).str.strip() == current_val)
                
                names_to, names_from = [], []
                # 渡す相手(to)と受ける相手(from)を特定
                for i, mask in enumerate([mask_h, mask_t]):
                    keys = t_s.loc[mask, t_s.columns[1]].unique()
                    # 他のスタッフのPDFデータから名前を紐付け
                    found = other_staff_shift[other_staff_shift.iloc[:, col].astype(str).str.strip().isin(keys)]
                    names = found.iloc[:, 0].unique().tolist()
                    if i == 0: names_to = names
                    else: names_from = names

                to_str = f"to {'・'.join(names_to)}" if names_to else ""
                from_str = f"from {'・'.join(names_from)}" if names_from else ""
                
                # 新しい詳細予定を追加
                final_rows.append([
                    f"{h_dep}{to_str}=>【{current_val}】{from_str}", 
                    target_date, 
                    str(t_s.iloc[0, t_col]).strip(), # 開始時刻
                    target_date, 
                    "", # 終了時刻（次のループで確定）
                    "False", 
                    "", 
                    key
                ])
        prev_val = current_val

# --- Streamlit UI ---
st.set_page_config(page_title="Shift Converter", layout="wide")
st.header("📅 シフトカレンダー一括変換完成版")

# サイドバーでPDFアップロード
uploaded_file = st.sidebar.file_uploader("PDFをアップロード", type="pdf")

if uploaded_file and st.sidebar.button("変換実行"):
    # (省略) Google APIの認証とExcel取得の呼び出し
    # service = get_gapi_service() 
    # location_dic = time_schedule_from_drive(service, TIME_TABLE_ID)
    
    y, m = extract_year_month(uploaded_file)
    my_s, other_s = pdf_reader(uploaded_file, "西村文宏")
    
    final_results = []
    # 1ヶ月分ループ
    for col in range(1, my_s.shape[1]):
        shift_code = str(my_s.iloc[0, col]).strip()
        if not shift_code or shift_code.lower() == "nan": continue
        
        target_date = f"{y}/{m}/{col}"
        
        # 休暇判定
        if any(h in shift_code for h in ["休", "有給", "公休"]):
            final_results.append([f"T2_休日", target_date, "", target_date, "", "True", "", "T2"])
        else:
            # 各勤務地（T2等）に対して詳細計算を実行
            # ここでは例として location_dic['T2'] を使用
            # shift_cal("T2", target_date, col, shift_code, other_s, location_dic['T2'][0], final_results)
            pass

    # 結果表示
    df_res = pd.DataFrame(final_results, columns=['Subject','Start Date','Start Time','End Date','End Time','All Day Event','Description','Location'])
    st.table(df_res)
    
    # CSVダウンロード
    csv = df_res.to_csv(index=False, encoding='utf-8-sig')
    st.download_button("Googleカレンダー用CSVを保存", csv, "shift_calendar.csv", "text/csv")
