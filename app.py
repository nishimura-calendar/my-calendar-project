import streamlit as st
import pandas as pd
import unicodedata
import re

# --- 比較用正規化関数 ---
def normalize_for_match(text):
    if text is None or str(text).lower() == 'nan':
        return ""
    normalized = unicodedata.normalize('NFKC', str(text))
    return re.sub(r'\s+', '', normalized).strip().upper()

# --- 打合.py参照：詳細シフト（引き継ぎ）計算ロジック ---
def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """
    通常シフトの詳細（時間別引き継ぎ）を計算し、final_rowsに格納する。
    昨日の修正（prev_valの更新位置）を反映済み。
    """
    shift_code = my_daily_shift.iloc[0, col]
    sched_clean = time_schedule.fillna("").astype(str)
    my_time_shift = sched_clean[sched_clean.iloc[:, 1] == shift_code]
                    
    if not my_time_shift.empty:
        prev_val = ""
        for t_col in range(2, time_schedule.shape[1]):
            current_val = my_time_shift.iloc[0, t_col]
            
            if current_val != prev_val:
                if current_val != "": 
                    handing_over_department = "" 
                    for i in range(2):
                        mask = pd.Series([False] * len(time_schedule))
                        if i == 0:
                            mask = (sched_clean.iloc[:, t_col] == prev_val) & (sched_clean.iloc[:, 1] != shift_code)
                        else:
                            mask = (sched_clean.iloc[:, t_col] == current_val) & (sched_clean.iloc[:, 1] != shift_code)
                        
                        search_keys = time_schedule.loc[mask, time_schedule.columns[1]]
                        target_rows = other_staff_shift[other_staff_shift.iloc[:, col].isin(search_keys)]
                        names_series = target_rows.iloc[:, 0]
                        
                        if i == 0:
                            staff_names = f"to {'・'.join(names_series.unique().astype(str))}" if not names_series.empty else ""
                            handing_over = f"{handing_over_department}{staff_names}"
                        else:
                            staff_names = f"from {'・'.join(names_series.unique().astype(str))}" if not names_series.empty else ""
                            taking_over = f"【{current_val}】{staff_names}"    
                    
                    final_rows.append([
                        f"{handing_over}=>{taking_over}", 
                        target_date, 
                        time_schedule.iloc[0, t_col], 
                        target_date, 
                        "", 
                        "False", 
                        "", 
                        ""
                    ])
                else:
                    if len(final_rows) > 0 and final_rows[-1][5] == "False":
                        final_rows[-1][4] = time_schedule.iloc[0, t_col]
            
            # 昨日の修正内容を維持
            prev_val = current_val

# --- メインロジック（打ち合わせ内容通り） ---
def process_daily_shift(items, key, date_str, master_df, master_areas_norm, my_daily_shift, other_staff_shift, current_col):
    final_rows = []
    
    # my_daily_shiftの項目通りに進める
    for item in items:
        if not item or str(item).strip() == "":
            continue
            
        norm_item = normalize_for_match(item)
        
        # --- 分岐1 ---
        # 値がtime_scheduleのB列にあれば
        if norm_item in master_areas_norm:
            # append(Subject=key+値, Start Date=my_daily_shiftから, All Day Event=True...)
            final_rows.append([
                f"{key}{item}", date_str, "", date_str, "", "True", "", ""
            ])
            # さらにtime_scheduleに沿って進める（打合.py参照）
            shift_cal(key, date_str, current_col, item, my_daily_shift, other_staff_shift, master_df, final_rows)
            
        # 値がtime_scheduleのB列になければ
        else:
            # append(Subject=値, Start Date=my_daily_shiftから, All Day Event=True...)
            final_rows.append([
                item, date_str, "", date_str, "", "True", "", ""
            ])

        # --- 分岐2 ---
        # もし"本町"なら（分岐1の処理の後にさらに追加）
        if "本町" in item:
            # Start Time=関数から抽出, End Time=関数から抽出, All Day Event=False
            try:
                start_t = master_df.iloc[0, 3] # 関数代わりの抽出
                end_t = master_df.iloc[0, -1]
            except:
                start_t, end_t = "09:00", "17:00"

            final_rows.append([
                item, date_str, start_t, date_str, end_t, "False", "", ""
            ])
                
    return final_rows

def main():
    st.title("勤務シフトCSV出力")
    
    if st.button("月間.csv を生成"):
        # テスト用パラメータ
        key = "大阪拠点"
        date_str = "2026-04-02"
        items = ["9①14", "本町", "有休", "会議メモ"] 
        
        # ダミーデータ
        master_df = pd.DataFrame([
            ["", "", "", "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00"],
            ["", "9①14", "A", "A", "休憩", "休憩", "B", "B", "B", "B", "B", "B"]
        ])
        master_areas_norm = ["9①14"]
        my_daily_shift = pd.DataFrame([["本人", "", "", "", "", "9①14"]])
        other_staff_shift = pd.DataFrame([["同僚", "", "", "", "", "8②15"]])
        current_col = 5

        # 実行
        all_data = process_daily_shift(items, key, date_str, master_df, master_areas_norm, my_daily_shift, other_staff_shift, current_col)
        
        df_final = pd.DataFrame(all_data, columns=['Subject', 'Start Date', 'Start Time', 'End Date', 'End Time', 'All Day Event', 'Description', 'Location'])
        
        st.write(df_final)
        
        csv = df_final.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(label="月間.csv をダウンロード", data=csv, file_name="月間.csv", mime="text/csv")

if __name__ == "__main__":
    main()
