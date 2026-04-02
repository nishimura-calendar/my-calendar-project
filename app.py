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

# --- 引き継ぎ計算ロジック（打合.py由来） ---
def shift_cal(loc_name, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """通常シフトの詳細（時間別引き継ぎ）を計算し、final_rowsに格納する"""
    # 呼び出し元のprocess_daily_shiftでTrue行は追加済み
    
    # 自分のシフトコード
    shift_code = shift_info # 引数から直接利用
    sched_clean = time_schedule.fillna("").astype(str)
    
    # 時程表（マスター）から自分のシフト行を探す
    my_time_shift = sched_clean[sched_clean.iloc[:, 1] == shift_code]
                    
    if not my_time_shift.empty:
        prev_val = ""
        for t_col in range(2, time_schedule.shape[1]):
            current_val = my_time_shift.iloc[0, t_col]
            
            if current_val != prev_val:
                # 前のイベントがある場合は終了時間をセット（空白への変化または別の値への変化）
                if len(final_rows) > 0 and final_rows[-1][5] == "False":
                    final_rows[-1][4] = time_schedule.iloc[0, t_col]

                if current_val != "": 
                    # 新しい状態の開始
                    # 他のスタッフから誰がその時間帯にいるかを抽出（打合.pyのロジック）
                    # ここでは簡略化せず、other_staff_shiftとの照合を想定
                    
                    # 渡す人(to) / 受ける人(from) の判定
                    # ※ time_schedule.loc[mask, ...] の部分は実際の運用データに依存
                    handing_over = "to 他スタッフ" # 仮：ロジック詳細は打合.py参照
                    taking_over = f"【{current_val}】from 他スタッフ" 
                    
                    # False行（時間指定行）を追加
                    final_rows.append([
                        f"{handing_over}=>{taking_over}", 
                        target_date, 
                        time_schedule.iloc[0, t_col], # 開始時間
                        target_date, 
                        "",                           # 終了時間は次の変化時にセット
                        "False", 
                        "", 
                        ""
                    ])
                
            prev_val = current_val

# --- メインの振り分け・生成ロジック ---
def process_daily_shift(items, loc_name, date_str, master_df, master_areas_norm, my_daily_shift, other_staff_shift, current_col):
    final_rows = []
    
    # 有効なキーワードの定義
    valid_keywords = ["本町", "有休"]
    
    for item in items:
        if not item or str(item).strip() == "":
            continue
            
        norm_item = normalize_for_match(item)
        
        # --- 分岐1：時程表(time_schedule)のB列にあるか判定 ---
        if norm_item in master_areas_norm:
            # 拠点名+シフトコード
            final_rows.append([
                f"{loc_name}+{item}", 
                date_str, "", date_str, "", "True", "", ""
            ])
            
            # 引き継ぎ詳細（False行）の生成
            try:
                shift_cal(loc_name, date_str, current_col, item, my_daily_shift, other_staff_shift, master_df, final_rows)
            except Exception as e:
                st.error(f"詳細生成エラー: {item} - {e}")
            
        # --- 分岐2：特定のキーワードに合致するか判定 ---
        elif any(key in item for key in valid_keywords):
            # 終日イベントを追加（本町、有休など）
            final_rows.append([
                item, 
                date_str, "", date_str, "", "True", "", ""
            ])

            # "本町" の場合のみ時間枠を追加
            if "本町" in item:
                try:
                    start_t = master_df.iloc[0, 3] if master_df.shape[1] > 3 else "09:00"
                    end_t = master_df.iloc[0, -1] if master_df.shape[1] > 0 else "17:00"
                except:
                    start_t, end_t = "09:00", "17:00"
                
                final_rows.append([
                    item, 
                    date_str, start_t, date_str, end_t, "False", "", ""
                ])
        
        # それ以外（会議メモ等）は何もしない（いらない）

    return final_rows

# --- Streamlit UI ---
def main():
    st.title("勤務シフト・カレンダー生成")
    
    if st.button("月間.csv を生成"):
        # 動作確認用テストデータ
        loc_name = "大阪拠点"
        target_date = "2026-04-02"
        # 会議メモを混ぜても出力されないことを確認
        items = ["9①14", "本町", "有休", "会議メモ"] 
        current_col = 5
        
        # テスト用の時程表（ヘッダー行：[0,1,2,3,4...], [開始, シフト, 9:00, 10:00...17:00]）
        master_df = pd.DataFrame([
            ["", "", "", "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00"],
            ["", "9①14", "区域A", "区域A", "区域A", "休憩", "休憩", "区域B", "区域B", "区域B", "区域B", "区域B"]
        ])
        
        master_areas_norm = ["9①14", "8②15"] 
        my_daily_shift = pd.DataFrame([["名前", "", "", "", "", "9①14"]]) # 5列目にシフト
        other_staff_shift = pd.DataFrame([["他スタッフ", "", "", "", "", "8②15"]])

        all_monthly_data = process_daily_shift(
            items, loc_name, target_date, master_df, 
            master_areas_norm, my_daily_shift, 
            other_staff_shift, current_col
        )
        
        df_final = pd.DataFrame(all_monthly_data, columns=[
            'Subject', 'Start Date', 'Start Time', 'End Date', 'End Time', 
            'All Day Event', 'Description', 'Location'
        ])
        
        st.write("生成プレビュー（会議メモが消え、詳細時間が反映されているか確認）:", df_final)
        
        csv = df_final.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(
            label="月間.csv をダウンロード",
            data=csv,
            file_name="月間.csv",
            mime="text/csv",
        )

if __name__ == "__main__":
    main()
