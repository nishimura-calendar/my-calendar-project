import streamlit as st
import pandas as pd
import practice_0 as p0
from datetime import datetime
import re

def main():
    st.set_page_config(page_title="勤務シフトCSV出力システム", layout="wide")
    st.title("勤務シフトCSV出力システム")

    # 1. サイドバーでの基本設定
    st.sidebar.header("ユーザー設定")
    target_staff = st.sidebar.text_input("本人の氏名 (PDF内と一致させる)", value="本人氏名")
    
    # 2. ファイルアップロード
    st.subheader("1. 勤務表PDFのアップロード")
    uploaded_pdf = st.file_uploader("PDFファイルを選択", type="pdf")
    
    # 3. 日付選択と列特定
    st.subheader("2. 対象日の設定")
    target_date = st.date_input("解析する日付", datetime(2026, 4, 2))
    date_str = target_date.strftime("%Y-%m-%d")
    
    # PDF内の日付列を特定 (例: 1日が3列目から始まる等のルール)
    current_col = target_date.day + 2 

    if uploaded_pdf:
        # A. PDF解析 (practice_0の関数を使用)
        pdf_dic = p0.pdf_reader(uploaded_pdf, target_staff)
        
        if not pdf_dic:
            st.error(f"PDFから「{target_staff}」が見つかりませんでした。氏名を確認してください。")
            return

        # B. 時程表の取得 (本来はGoogle Drive連携。ここではデモデータを生成)
        # 実際にはここで drive 連携ロジックを呼び出し、{拠点名: DF} の辞書を作る
        st.info("時程表（Excel/Google Sheets）を読み込み中...")
        # デモ用時程表辞書
        time_dic = {
            "大阪拠点": pd.DataFrame([
                ["", "", "", "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00"],
                ["", "9①14", "A部署", "A部署", "休憩", "休憩", "B部署", "B部署", "B部署", "B部署", "B部署", "B部署"]
            ])
        }

        # 4. 実行ボタン
        if st.button("CSVデータを生成"):
            # C. データの紐付け (data_integration)
            integrated_data = p0.data_integration(pdf_dic, time_dic)
            
            if not integrated_data:
                st.warning("時程表との紐付けに失敗しました。拠点名が一致しているか確認してください。")
                st.write("PDFから検出された拠点:", list(pdf_dic.keys()))
                return

            # D. CSV行の生成
            final_rows = p0.process_integrated_data(integrated_data, date_str, current_col)
            
            # E. 結果表示とダウンロード
            df_final = pd.DataFrame(final_rows, columns=[
                'Subject', 'Start Date', 'Start Time', 'End Date', 'End Time', 
                'All Day Event', 'Description', 'Location'
            ])
            
            st.success(f"{len(df_final)}件の予定を生成しました。")
            st.dataframe(df_final)
            
            csv_binary = df_final.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button(
                label="📥 月間.csv をダウンロード",
                data=csv_binary,
                file_name=f"月間_{date_str.replace('-','')}.csv",
                mime="text/csv"
            )

if __name__ == "__main__":
    main()
