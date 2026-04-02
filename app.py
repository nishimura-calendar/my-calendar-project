import streamlit as st
import pandas as pd
import practice_0 as p0
from datetime import datetime

def main():
    st.set_page_config(page_title="勤務シフトCSV出力", layout="wide")
    st.title("勤務シフトCSV出力")

    # 1. PDFアップロード
    uploaded_pdf = st.file_uploader("勤務表PDFをアップロード", type="pdf")
    
    # 2. パラメータ設定
    target_date = st.date_input("対象日", datetime(2026, 4, 2))
    date_str = target_date.strftime("%Y-%m-%d")
    target_staff = "本人氏名" # 本来は設定等から取得
    
    if uploaded_pdf:
        # --- 実行プロセス ---
        
        # A. PDFから場所ごとの本人・他人データを抽出
        # ※practice_0.py の既存の pdf_reader を使用
        pdf_dic = p0.pdf_reader(uploaded_pdf, target_staff)
        
        # B. Google Drive から時程表を取得 (紐付けキー: 勤務地)
        # ※app.pyの修正箇所に基づき取得
        # time_schedule_dic = { "大阪拠点": df, "T2": df, ... }
        # ここでは service 等が準備されている前提
        time_schedule_dic = {} # 仮：実際は p0.time_schedule_from_drive()
        
        if st.button("月間.csv を生成"):
            # C. データの紐付け (data_integration)
            integrated_data = p0.data_integration(pdf_dic, time_schedule_dic)
            
            if not integrated_data:
                st.error("紐付けに失敗しました。PDFの勤務地と時程表の名前が一致しているか確認してください。")
                return

            # D. CSV行の生成
            # 列番号(current_col)は日付から特定するロジックが必要
            current_col = 5 
            final_rows = p0.process_integrated_data(integrated_data, date_str, current_col)
            
            # E. CSV出力
            df_final = pd.DataFrame(final_rows, columns=[
                'Subject', 'Start Date', 'Start Time', 'End Date', 'End Time', 
                'All Day Event', 'Description', 'Location'
            ])
            
            st.subheader("出力プレビュー")
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
