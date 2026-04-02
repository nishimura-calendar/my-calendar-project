import streamlit as st
import pandas as pd
import practice_0 as p0
from datetime import datetime
import io

def main():
    st.set_page_config(page_title="勤務シフトCSV出力システム", layout="wide")
    st.title("勤務シフトCSV出力システム")

    target_staff = st.sidebar.text_input("本人の氏名", value="西村文宏")
    target_date = st.sidebar.date_input("解析対象日", datetime(2026, 1, 1))
    
    # 基本事項：スプレッドシートID
    sheet_id = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

    uploaded_pdf = st.file_uploader("勤務表PDFをアップロード", type="pdf")

    if uploaded_pdf:
        # 1. 時程表の取得 (Excelダウンロード経由)
        try:
            service = p0.get_gdrive_service(st.secrets)
            time_dic = p0.time_schedule_from_drive(service, sheet_id)
        except Exception as e:
            st.error(f"時程表取得エラー: {e}")
            return

        # 2. PDF解析
        pdf_dic = p0.pdf_reader(uploaded_pdf, target_staff)
        
        if pdf_dic:
            # 3. 紐付け
            integrated_data = p0.data_integration(pdf_dic, time_dic)
            
            # 4. 行生成
            target_date_str = target_date.strftime("%Y-%m-%d")
            # PDFの列：1日が index 1 になるよう調整が必要な場合はここを修正
            current_col = target_date.day 
            
            final_rows = p0.process_integrated_data(integrated_data, target_date_str, current_col)
            
            if final_rows:
                columns = ["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location"]
                df_final = pd.DataFrame(final_rows, columns=columns)
                
                st.markdown("### 📅 CSVプレビュー")
                st.dataframe(df_final)
                
                csv_buffer = io.StringIO()
                df_final.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
                
                st.download_button(
                    label="月間.csv をダウンロード",
                    data=csv_buffer.getvalue(),
                    file_name=f"月間_{target_staff}_{target_date_str}.csv",
                    mime="text/csv",
                )

if __name__ == "__main__":
    main()
