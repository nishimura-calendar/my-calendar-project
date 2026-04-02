import streamlit as st
import pandas as pd
import unicodedata
import re
import pdfplumber
from datetime import datetime

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
    """
    shift_code = my_daily_shift.iloc[0, col]
    sched_clean = time_schedule.fillna("").astype(str)
    # 時程表の2列目（index 1）から自分のシフトコードを探す
    my_time_shift = sched_clean[sched_clean.iloc[:, 1] == shift_code]
                    
    if not my_time_shift.empty:
        prev_val = ""
        # 3列目（index 2）以降が時間枠
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
            
            # 昨日の重要事項：prev_valの更新をループの最後で行う
            prev_val = current_val

# --- メインロジック（打ち合わせ内容通りの分岐） ---
def process_daily_shift(items, key, date_str, master_df, master_areas_norm, my_daily_shift, other_staff_shift, current_col):
    final_rows = []
    
    # my_daily_shift通り（itemsの順）に進めて
    for item in items:
        if not item or str(item).strip() == "":
            continue
            
        norm_item = normalize_for_match(item)
        
        # --- 分岐1 ---
        # 値がtime_scheduleのB列にあれば
        if norm_item in master_areas_norm:
            # append(Subject=key+値, Start Date=my_daily_shiftから, Start Time="", End Date=my_daily_shiftから, End Time="", All Day Event=True, ...)
            final_rows.append([
                f"{key}{item}", date_str, "", date_str, "", "True", "", ""
            ])
            # さらにtime_scheduleに沿って進める（打合.py参照：紐付け処理）
            shift_cal(key, date_str, current_col, item, my_daily_shift, other_staff_shift, master_df, final_rows)
            
        # 値がtime_scheduleのB列になければ
        else:
            # append(Subject=値, Start Date=my_daily_shiftから, Start Time="", End Date=my_daily_shiftから, End Time="", All Day Event=True, ...)
            final_rows.append([
                item, date_str, "", date_str, "", "True", "", ""
            ])

        # --- 分岐2 ---
        # もし"本町"なら（分岐1とは独立して、条件に合致すればさらに行を追加）
        if "本町" in item:
            # append(Subject=値, Start Date=my_daily_shiftから, Start Time=関数から抽出, End Time=関数から抽出, All Day Event=False, ...)
            try:
                start_t = master_df.iloc[0, 3] # マスタのヘッダー等から時間を抽出
                end_t = master_df.iloc[0, -1]
            except:
                start_t, end_t = "09:00", "17:00"

            final_rows.append([
                item, date_str, start_t, date_str, end_t, "False", "", ""
            ])
                
    return final_rows

def main():
    st.set_page_config(page_title="勤務シフトCSV出力", layout="wide")
    st.title("📅 勤務シフトCSV出力ツール")

    st.sidebar.header("ファイルのアップロード")
    uploaded_pdf = st.sidebar.file_uploader("シフトPDFを選択してください", type="pdf")
    
    st.sidebar.markdown("---")
    st.sidebar.header("設定")
    key = st.sidebar.text_input("拠点名", value="大阪拠点")

    if uploaded_pdf is not None:
        st.success("PDFを受領しました。")
        
        if st.button("月間.csv を生成"):
            # PDFから予定（items）と他スタッフデータを取得する処理（昨日の反映事項）
            # ここでは解析結果を想定
            items = ["9①14", "本町", "有休", "会議メモ"] 
            date_str = "2026-04-02"
            
            # 時程表（Google Drive等から取得したマスタ）
            # B列にシフトコードがある構造
            master_df = pd.DataFrame([
                ["", "", "", "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00"],
                ["", "9①14", "A部署", "A部署", "休憩", "休憩", "B部署", "B部署", "B部署", "B部署", "B部署", "B部署"]
            ])
            
            # B列のコードを正規化してリスト化
            master_areas_norm = [normalize_for_match(x) for x in master_df.iloc[:, 1].tolist()]
            
            # スタッフデータ
            my_daily_shift = pd.DataFrame([["本人", "", "", "", "", "9①14"]])
            other_staff_shift = pd.DataFrame([["同僚A", "", "", "", "", "8②15"]])
            current_col = 5

            # メイン処理（打ち合わせ内容通りの分岐）
            all_data = process_daily_shift(
                items, key, date_str, master_df, master_areas_norm, 
                my_daily_shift, other_staff_shift, current_col
            )
            
            # 結果をDataFrameにまとめてCSV出力
            df_final = pd.DataFrame(all_data, columns=[
                'Subject', 'Start Date', 'Start Time', 'End Date', 'End Time', 
                'All Day Event', 'Description', 'Location'
            ])
            
            st.subheader("生成結果プレビュー")
            st.dataframe(df_final)
            
            csv = df_final.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button(
                label="📥 月間.csv をダウンロード", 
                data=csv, 
                file_name=f"月間_{datetime.now().strftime('%m%d')}.csv", 
                mime="text/csv"
            )

if __name__ == "__main__":
    main()
