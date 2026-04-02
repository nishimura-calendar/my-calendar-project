import streamlit as st
import pandas as pd
import pdfplumber
from datetime import datetime
import unicodedata
import re
import io

# --- 比較用正規化関数 ---
def normalize_for_match(text):
    if text is None or str(text).lower() == 'nan':
        return ""
    normalized = unicodedata.normalize('NFKC', str(text))
    # スペース削除、大文字化
    return re.sub(r'\s+', '', normalized).strip().upper()

# --- 引き継ぎ計算ロジック（打合.py由来の確定版） ---
def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """
    通常シフトの詳細（時間別引き継ぎ）を計算し、final_rowsに格納する。
    打合.pyのロジックに基づき、他のスタッフとの引き継ぎ相手を特定します。
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
                    # 状態の変化があった場合、新しい時間帯の開始
                    handing_over_department = "" 
                    
                    # 引き継ぎ相手の探索（i=0: 渡す相手, i=1: 受ける相手）
                    for i in range(2):
                        # 打合.pyのロジック: 同じ時間帯に自分とは別の場所にいる人などを特定
                        mask = pd.Series([False] * len(time_schedule))
                        # ※ここでは打合.pyの条件式を想定（簡略化せず構造を維持）
                        # prev_val(渡す) / current_val(受ける) に基づくマスク処理
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
                    
                    # False行（時間指定行）の追加
                    final_rows.append([
                        f"{handing_over}=>{taking_over}", 
                        target_date, 
                        time_schedule.iloc[0, t_col], # 開始時間（ヘッダー行）
                        target_date, 
                        "",                           # 終了時間は次の変化時にセット
                        "False", 
                        "", 
                        ""
                    ])
                else:
                    # 空白になった場合は直前のFalse行に終了時間をセット
                    if len(final_rows) > 0 and final_rows[-1][5] == "False":
                        final_rows[-1][4] = time_schedule.iloc[0, t_col]
            
            prev_val = current_val

# --- メインの振り分け・生成ロジック ---
def process_daily_shift(items, loc_name, date_str, master_df, master_areas_norm, my_daily_shift, other_staff_shift, current_col):
    final_rows = []
    valid_keywords = ["本町", "有休"]
    
    for item in items:
        if not item or str(item).strip() == "":
            continue
            
        norm_item = normalize_for_match(item)
        
        # 分岐1：時程表(time_schedule)のB列にあるか判定
        if norm_item in master_areas_norm:
            # 1. 終日イベントを追加（拠点名+値）
            final_rows.append([
                f"{loc_name}+{item}", 
                date_str, "", date_str, "", "True", "", ""
            ])
            
            # 2. 引き継ぎ詳細（False行）の生成（打合.pyロジック）
            try:
                shift_cal(loc_name, date_str, current_col, item, my_daily_shift, other_staff_shift, master_df, final_rows)
            except Exception as e:
                st.error(f"詳細生成エラー: {item}")
            
        # 分岐2：特定のキーワード（本町・有休）
        elif any(key in item for key in valid_keywords):
            final_rows.append([
                item, 
                date_str, "", date_str, "", "True", "", ""
            ])

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
                
    return final_rows

# --- Streamlit UI ---
def main():
    st.set_page_config(page_title="カレンダー生成ツール", layout="wide")
    st.title("📅 勤務シフト変換ツール")

    # サイドバー
    st.sidebar.header("1. ファイル準備")
    uploaded_pdf = st.sidebar.file_uploader("シフトPDFをアップロード", type="pdf")
    
    st.sidebar.markdown("---")
    st.sidebar.header("2. 設定")
    loc_name = st.sidebar.text_input("拠点名", value="大阪拠点")

    if uploaded_pdf is not None:
        st.success(f"ファイルを受領しました: {uploaded_pdf.name}")
        
        if st.button("解析して月間.csvを作成"):
            # ※本来はPDF解析ロジックが入りますが、ご要望により打合せ内容のロジックに集中します
            # ここではmy_daily_shift（個人の予定）から抽出された項目を想定
            items = ["9①14", "本町", "有休"] # 解析結果の例
            target_date = "2026-04-02"
            current_col = 5
            
            # 時程表（マスター）のダミーデータ
            master_df = pd.DataFrame([
                ["", "", "", "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00"],
                ["", "9①14", "受付", "受付", "休憩", "休憩", "巡回", "巡回", "窓口", "窓口", "窓口", "窓口"]
            ])
            master_areas_norm = ["9①14", "8②15"] 
            
            # 他のスタッフのシフト状況（引き継ぎ相手特定用）
            my_daily_shift = pd.DataFrame([["本人", "", "", "", "", "9①14"]])
            other_staff_shift = pd.DataFrame([["スタッフA", "", "", "", "", "8②15"]])

            # 変換ロジック実行
            all_monthly_data = process_daily_shift(
                items, loc_name, target_date, master_df, 
                master_areas_norm, my_daily_shift, 
                other_staff_shift, current_col
            )
            
            df_final = pd.DataFrame(all_monthly_data, columns=[
                'Subject', 'Start Date', 'Start Time', 'End Date', 'End Time', 
                'All Day Event', 'Description', 'Location'
            ])
            
            st.subheader("📋 生成プレビュー")
            st.dataframe(df_final)
            
            csv = df_final.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button(
                label="📥 月間.csv をダウンロード",
                data=csv,
                file_name=f"月間_{datetime.now().strftime('%m%d')}.csv",
                mime="text/csv",
            )
    else:
        st.warning("PDFをアップロードしてください。")

if __name__ == "__main__":
    main()
