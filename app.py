import streamlit as st
import pandas as pd
import practice_0 as p0
from datetime import datetime

def main():
    st.set_page_config(page_title="勤務シフトCSV出力システム", layout="wide")
    st.title("勤務シフトCSV出力システム")

    st.sidebar.header("ユーザー設定")
    target_staff = st.sidebar.text_input("本人の氏名", value="本人氏名")
    
    st.subheader("1. 勤務表PDFのアップロード")
    uploaded_pdf = st.file_uploader("PDFファイルを選択", type="pdf")
    
    st.subheader("2. 対象日の設定")
    target_date = st.date_input("解析する日付（列特定用）", datetime(2026, 4, 2))
    
    # 日付列を特定 (例: 1日=3列目なら day + 2)
    current_col = target_date.day + 2 

    if uploaded_pdf:
        # A. PDF解析 (昨日と同じ戻り値1つの形式)
        pdf_dic = p0.pdf_reader(uploaded_pdf, target_staff)
        
        if not pdf_dic:
            st.error(f"PDFから「{target_staff}」が見つかりませんでした。")
            return

        # B. 時程表の取得 (デモデータ)
        # 実際にはここに Google Drive 連携コードが入ります
        time_dic = {
            "大阪拠点": pd.DataFrame([
                ["", "", "", "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00"],
                ["", "9①14", "A部署", "A部署", "休憩", "休憩", "B部署", "B部署", "B部署", "B部署", "B部署", "B部署"]
            ])
        }

        if st.button("CSVデータを生成"):
            # C. データの紐付け
            integrated_data = p0.data_integration(pdf_dic, time_dic)
            
            if not integrated_data:
                st.warning("時程表との紐付けに失敗しました。")
                st.write("PDFから検出された拠点:", list(pdf_dic.keys()))
                return

            # D. CSV行の生成 (UIで選択した日付を使用)
            target_date_str = target_date.strftime("%Y-%m-%d")
            final_rows = p0.process_integrated_data(integrated_data, target_date_str, current_col)
            
            df_final = pd.DataFrame(final_rows, columns=[
                'Subject', 'Start Date', 'Start Time', 'End Date', 'End Time', 
                'All Day Event', 'Description', 'Location'
            ])
            
            st.dataframe(df_final)
            
            csv_binary = df_final.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button(
                label="📥 月間.csv をダウンロード",
                data=csv_binary,
                file_name="月間.csv",
                mime="text/csv"
            )

if __name__ == "__main__":
    main()
