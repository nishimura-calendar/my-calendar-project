import streamlit as st
import pandas as pd
import unicodedata
import re
from practice_0 import pdf_reader, extract_year_month, time_schedule_from_drive

def shift_cal(key, target_date, col, shift_info, other_staff_shift, time_schedule, final_rows):
    """15分ごとの場所移動と引き継ぎ相手を計算"""
    clean_info = unicodedata.normalize('NFKC', str(shift_info)).strip()
    t_s = time_schedule.copy()
    
    # 自分の記号と一致する行を探す
    my_time_shift = t_s[t_s.iloc[:, 1].astype(str).apply(lambda x: unicodedata.normalize('NFKC', x).strip()) == clean_info]
    
    if not my_time_shift.empty:
        # 終日予定（背景用）
        final_rows.append([f"{key}_{clean_info}", target_date, "", target_date, "", "True", "", key])
        
        prev_val = ""
        # 2列目(時刻開始)から最後までスキャン
        for t_col in range(2, t_s.shape[1]):
            raw_val = my_time_shift.iloc[0, t_col]
            current_val = str(raw_val).strip() if pd.notna(raw_val) and str(raw_val).lower() != "nan" and str(raw_val) != "" else ""
            
            if current_val != prev_val:
                if current_val != "":
                    # 交代・移動の判定
                    h_dep = ""
                    mask_h = pd.Series([False] * len(t_s))
                    if prev_val == "":
                        mask_h = (t_s.iloc[:, t_col].astype(str).replace('nan','') == "") & (t_s.iloc[:, t_col-1].astype(str).replace('nan','') != "")
                        if mask_h.any(): h_dep = "(交代)"
                    else:
                        h_dep = f"({prev_val})"
                        mask_h = (t_s.iloc[:, t_col].astype(str).str.strip() == prev_val)
                        if len(final_rows) > 0 and final_rows[-1][5] == "False":
                            final_rows[-1][4] = str(t_s.iloc[0, t_col]).strip() # 前の予定の終了時刻

                    # 受ける側の判定
                    mask_t = (t_s.iloc[:, t_col-1].astype(str).str.strip() == current_val)
                    
                    h_over, t_over = "", ""
                    for i in range(2):
                        mask = mask_h if i == 0 else mask_t
                        keys = t_s.loc[mask, t_s.columns[1]].unique()
                        names = other_staff_shift[other_staff_shift.iloc[:, col].astype(str).str.strip().isin(keys)].iloc[:, 0].unique()
                        if i == 0: h_over = f"{h_dep}to {'・'.join(names)}" if names.any() else f"{h_dep}"
                        else: t_over = f"【{current_val}】from {'・'.join(names)}" if names.any() else f"【{current_val}】"

                    final_rows.append([f"{h_over}=>{t_over}", target_date, str(t_s.iloc[0, t_col]).strip(), target_date, "", "False", "", key])
                else:
                    if len(final_rows) > 0 and final_rows[-1][5] == "False":
                        final_rows[-1][4] = str(t_s.iloc[0, t_col]).strip()
            prev_val = current_val

# --- Streamlit UI 部分 ---
st.title("📅 シフトカレンダー変換完成版")
# (Google API認証、ファイル選択等の既存コード...)

if st.button("変換開始"):
    # (PDF読み込み、データ統合処理...)
    # 最終的なループ処理の中で shift_cal を呼び出す
    final_results = []
    # ... (PDFループ、日付ループ)
    # shift_cal(work_place, target_date, col, shift_code, other_s, t_schedule, final_results)
    
    df_res = pd.DataFrame(final_results, columns=['Subject','Start Date','Start Time','End Date','End Time','All Day Event','Description','Location'])
    st.table(df_res)
