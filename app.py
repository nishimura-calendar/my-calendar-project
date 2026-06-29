import streamlit as st
import calendar
import camelot
import os
import re

# PDFから日付相当の数字を抽出してリストで返す関数
def get_dates_from_pdf(pdf_file_path):
    tables = camelot.read_pdf(pdf_file_path, pages='1', flavor='stream')
    if not tables:
        return []
    
    # テーブルデータ全体から数字を抽出
    df = tables[0].df
    all_data = df.astype(str).values.flatten()
    
    days = []
    for v in all_data:
        clean_v = v.strip().replace('.0', '')
        # 1〜31の数字を抽出
        if clean_v.isdigit():
            num = int(clean_v)
            if 1 <= num <= 31:
                days.append(num)
    return sorted(list(set(days))), tables[0].df

# --- メイン処理 ---
def main():
    st.title("シフトカレンダー作成システム")
    uploaded_file = st.file_uploader("読み込むpdfシフトファイルを開いてください。", type="pdf")
    
    if uploaded_file:
        # 年月の入力
        year_a = st.number_input("年", value=2026)
        month_a = st.number_input("月", value=3)

        if st.button("実行"):
            temp_path = "temp_shift.pdf"
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            # PDF解析
            found_days, df_table = get_dates_from_pdf(temp_path)
            last_day_b = max(found_days) if found_days else 0
            count_b = len(found_days)
            
            # 期待される月末日
            _, last_day_a = calendar.monthrange(int(year_a), int(month_a))
            
            st.write(f"--- 診断結果 ---")
            st.write(f"期待される月末日: {last_day_a}日")
            st.write(f"PDFから検出した日付の数: {count_b}個")
            st.write(f"PDFから検出した最大の日付: {last_day_b}日")

            if count_b == last_day_a:
                st.success("第1関門突破！")
            else:
                st.error(f"整合性エラー: 期待値 {last_day_a} に対して PDFの日付認識数が一致しません。")
                
                st.write("### PDFファイルの内容（テーブル形式）")
                st.dataframe(df_table) # 加工なしでそのまま表示
                
                st.stop() # 処理を停止

            if os.path.exists(temp_path):
                os.remove(temp_path)

if __name__ == "__main__":
    main()
