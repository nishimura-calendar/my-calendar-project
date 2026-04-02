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
    return re.sub(r'\s+', '', normalized).strip().upper()

# --- 引き継ぎ計算ロジック（打合.py由来） ---
def shift_cal(loc_name, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """通常シフトの詳細（時間別引き継ぎ）を計算し、final_rowsに格納する"""
    shift_code = shift_info
    sched_clean = time_schedule.fillna("").astype(str)
    
    # 時程表から自分のシフト行を探す
    my_time_shift = sched_clean[sched_clean.iloc[:, 1] == shift_code]
                    
    if not my_time_shift.empty:
        prev_val = ""
        for t_col in range(2, time_schedule.shape[1]):
            current_val = my_time_shift.iloc[0, t_col]
            
            if current_val != prev_val:
                # 前のイベントの終了時間を更新
                if len(final_rows) > 0 and final_rows[-1][5] == "False":
                    final_rows[-1][4] = time_schedule.iloc[0, t_col]

                if current_val != "": 
                    # 新しい状態の開始
                    # ※ここでのhanding_over等の判定は本来の打合.pyのロジックに依存します
                    handing_over = "to 他スタッフ"
                    taking_over = f"【{current_val}】from 他スタッフ" 
                    
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
            prev_val = current_val

# --- メインの振り分け・生成ロジック ---
def process_daily_shift(items, loc_name, date_str, master_df, master_areas_norm, my_daily_shift, other_staff_shift, current_col):
    final_rows = []
    valid_keywords = ["本町", "有休"]
    
    for item in items:
        if not item or str(item).strip() == "":
            continue
            
        norm_item = normalize_for_match(item)
        
        # 分岐1：時程表のB列にあるか
        if norm_item in master_areas_norm:
            final_rows.append([
                f"{loc_name}+{item}", 
                date_str, "", date_str, "", "True", "", ""
            ])
            try:
                shift_cal(loc_name, date_str, current_col, item, my_daily_shift, other_staff_shift, master_df, final_rows)
            except Exception as e:
                st.error(f"詳細生成エラー: {item}")
            
        # 分岐2：本町・有休
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

    st.info("1. PDFをアップロード → 2. 解析 → 3. CSVダウンロード の流れで進めます。")

    # サイドバーで設定
    st.sidebar.header("1. ファイル設定")
    uploaded_pdf = st.sidebar.file_uploader("シフトPDFを選択してください", type="pdf")
    
    # 2. 時程表の取得（本来はGoogle Driveからですが、今は手動アップロードまたは仮データ）
    st.sidebar.markdown("---")
    st.sidebar.header("2. 時程表設定")
    st.sidebar.write("※Google Drive連携が未完了のため、現在はデモ用データを使用します。")

    if uploaded_pdf is not None:
        st.success(f"PDFを受領しました: {uploaded_pdf.name}")
        
        if st.button("シフトを解析してCSVを作成"):
            # PDF解析（簡易的な例）
            with pdfplumber.open(uploaded_pdf) as pdf:
                # 1ページ目を解析
                text = pdf.pages[0].extract_text()
                # ここでPDFから my_daily_shift（個人の予定）を見つける処理が入ります
                # 現時点では、デモとしてご提示のあったデータを使います
                items = ["9①14", "本町", "有休", "会議メモ"] 
            
            # --- 実行用パラメータ ---
            loc_name = "大阪拠点"
            target_date = "2026-04-02"
            current_col = 5
            
            # 仮の時程表（実際はDriveから取得）
            master_df = pd.DataFrame([
                ["", "", "", "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00"],
                ["", "9①14", "区域A", "区域A", "区域A", "休憩", "休憩", "区域B", "区域B", "区域B", "区域B", "区域B"]
            ])
            master_areas_norm = ["9①14", "8②15"] 
            my_daily_shift = pd.DataFrame([["名前", "", "", "", "", "9①14"]])
            other_staff_shift = pd.DataFrame([["他スタッフ", "", "", "", "", "8②15"]])

            # 変換ロジック実行
            all_monthly_data = process_daily_shift(
                items, loc_name, target_date, master_df, 
                master_areas_norm, my_daily_shift, 
                other_staff_shift, current_col
            )
            
            # データフレーム作成
            df_final = pd.DataFrame(all_monthly_data, columns=[
                'Subject', 'Start Date', 'Start Time', 'End Date', 'End Time', 
                'All Day Event', 'Description', 'Location'
            ])
            
            st.subheader("📊 生成された予定のプレビュー")
            st.dataframe(df_final)
            
            # CSV変換
            csv = df_final.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            
            st.markdown("---")
            st.subheader("3. ダウンロード")
            st.download_button(
                label="📥 月間.csv をダウンロードする",
                data=csv,
                file_name=f"月間_{datetime.now().strftime('%m%d')}.csv",
                mime="text/csv",
            )
    else:
        st.warning("左側のメニューからPDFファイルをアップロードしてください。")

if __name__ == "__main__":
    main()
