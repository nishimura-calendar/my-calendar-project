import streamlit as st
import pandas as pd
from datetime import datetime
import unicodedata
import re

# --- 比較用正規化関数 ---
def normalize_for_match(text):
    if text is None or str(text).lower() == 'nan':
        return ""
    normalized = unicodedata.normalize('NFKC', str(text))
    return re.sub(r'\s+', '', normalized).strip().upper()

# --- 打合.py から移植した引き継ぎ計算ロジック ---
def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """通常シフトの詳細（時間別引き継ぎ）を計算し、final_rowsに格納する"""
    # 注: 終日イベント(True)は呼び出し元(process_daily_shift)で既に追加済みのため、
    # ここでは詳細な引き継ぎ(False行)の生成に専念します。
    
    shift_code = my_daily_shift.iloc[0, col]
    sched_clean = time_schedule.fillna("").astype(str)
    my_time_shift = sched_clean[sched_clean.iloc[:, 1] == shift_code]
                    
    if not my_time_shift.empty:
        prev_val = ""
        for t_col in range(2, time_schedule.shape[1]):
            current_val = my_time_shift.iloc[0, t_col]
            
            if current_val != prev_val:
                if current_val != "": 
                    # 状態の変化があった場合、新しい時間帯の開始
                    handing_over_department = "" 
                    mask_handing_over = pd.Series([False] * len(time_schedule))
                    mask_taking_over = pd.Series([False] * len(time_schedule))
                    
                    # 引き継ぎ相手の探索ロジック
                    for i in range(2):
                        mask = mask_handing_over if i == 0 else mask_taking_over
                        search_keys = time_schedule.loc[mask, time_schedule.columns[1]]
                        target_rows = other_staff_shift[other_staff_shift.iloc[:, col].isin(search_keys)]
                        names_series = target_rows.iloc[:, 0]
                        
                        if i == 0:
                            staff_names = f"to {'・'.join(names_series.unique().astype(str))}" if not names_series.empty else ""
                            handing_over = f"{handing_over_department}{staff_names}"
                        else:
                            staff_names = f"from {'・'.join(names_series.unique().astype(str))}" if not names_series.empty else ""
                            taking_over = f"【{current_val}】{staff_names}"    
                    
                    # False行の追加
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
                    # 空白になった場合は前のイベントの終了時間をセット
                    if len(final_rows) > 0 and final_rows[-1][5] == "False":
                        final_rows[-1][4] = time_schedule.iloc[0, t_col]
                
                prev_val = current_val

# --- メインの振り分け・生成ロジック ---
def process_daily_shift(items, loc_name, date_str, master_df, master_areas_norm, my_daily_shift, other_staff_shift, current_col):
    final_rows = []
    
    for item in items:
        if not item:
            continue
            
        norm_item = normalize_for_match(item)
        
        # --- 分岐1：time_scheduleのB列（巡回区域）にあるか判定 ---
        if norm_item in master_areas_norm:
            # 1. 終日イベントを追加（Subject = 拠点名+値, Location = ""）
            final_rows.append([
                f"{loc_name}+{item}", # Subject
                date_str, "", date_str, "", "True", "", ""
            ])
            
            # 2. 引き継ぎ処理（打合.py由来のロジックを実行）
            try:
                shift_cal(loc_name, date_str, current_col, item, my_daily_shift, other_staff_shift, master_df, final_rows)
            except Exception as e:
                st.error(f"引き継ぎ計算中にエラーが発生しました: {item} - {e}")
            
        else:
            # --- B列にない場合（有休、本町、その他のメモなど） ---
            # 1. 終日イベントを追加（Subject = 値そのまま, Location = ""）
            final_rows.append([
                item, 
                date_str, "", date_str, "", "True", "", ""
            ])

            # --- 分岐2：もし "本町" なら詳細時間の追加処理 ---
            if "本町" in item:
                try:
                    # 時程表ヘッダーから開始(D列/index3)・終了(最終列)時間を取得
                    start_t = master_df.iloc[0, 3] if master_df.shape[1] > 3 else ""
                    end_t = master_df.iloc[0, -1] if master_df.shape[1] > 0 else ""
                except:
                    start_t, end_t = "", ""
                
                final_rows.append([
                    item, 
                    date_str, start_t, date_str, end_t, "False", "", ""
                ])
                
    return final_rows

# --- Streamlit UI ---
def main():
    st.title("勤務シフト・カレンダー生成")
    
    # 実際にはここで PDF解析やマスター取得を行いますが、
    # 今回は動作確認用にデモ用ボタンを配置します。
    if st.button("月間.csv を生成"):
        # ダミーデータの構成
        loc_name = "大阪拠点"
        date_str = datetime.now().strftime("%Y-%m-%d")
        items = ["9①14", "本町", "有休"]
        current_col = 5 # 例：PDF解析で得られた列番号
        
        # 空のデータフレーム等を準備（本来は実データが入ります）
        master_df = pd.DataFrame() 
        master_areas_norm = ["9①14", "8②15"] 
        my_daily_shift = pd.DataFrame()
        other_staff_shift = pd.DataFrame()

        # メインロジック実行
        all_monthly_data = process_daily_shift(
            items, loc_name, date_str, master_df, 
            master_areas_norm, my_daily_shift, 
            other_staff_shift, current_col
        )
        
        # 出力
        df_final = pd.DataFrame(all_monthly_data, columns=[
            'Subject', 'Start Date', 'Start Time', 'End Date', 'End Time', 
            'All Day Event', 'Description', 'Location'
        ])
        
        st.write("プレビュー:", df_final)
        
        csv = df_final.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(
            label="月間.csv をダウンロード",
            data=csv,
            file_name="月間.csv",
            mime="text/csv",
        )

if __name__ == "__main__":
    main()
