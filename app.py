import streamlit as st
import pandas as pd
import practice_0 as p0
from datetime import datetime
import io

def main():
    st.set_page_config(page_title="勤務シフトCSV出力システム", layout="wide")
    st.title("勤務シフトCSV出力システム")

    # --- サイドバー設定 ---
    st.sidebar.header("⚙️ 設定")
    target_staff = st.sidebar.text_input("本人の氏名", value="西村文宏")
    target_date = st.sidebar.date_input("解析対象日", datetime(2026, 1, 1))
    
    # 基本事項：スプレッドシートID
    sheet_id = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

    # --- ファイルアップロード ---
    st.subheader("📁 勤務表PDFのアップロード")
    uploaded_pdf = st.file_uploader("勤務表PDFを選択してください", type="pdf")

    # --- 解析実行ボタン ---
    analyze_button = st.sidebar.button("解析を実行する", type="primary")

    if uploaded_pdf:
        if analyze_button:
            # 1. 時程表の取得 (Excelダウンロード経由)
            with st.spinner("Google Driveから時程表を取得中..."):
                try:
                    service = p0.get_gdrive_service(st.secrets)
                    # XLSXとしてダウンロードして読み込むことで型崩れを防ぐ
                    time_dic = p0.time_schedule_from_drive(service, sheet_id)
                    
                    if not time_dic:
                        st.warning("時程表データが見つかりませんでした。")
                        return
                except Exception as e:
                    st.error(f"時程表取得エラー: {e}")
                    return

            # 2. PDF解析 (勤務地特定 -> スタッフ検索)
            with st.spinner("PDFを解析中..."):
                pdf_dic = p0.pdf_reader(uploaded_pdf, target_staff)
            
            if pdf_dic:
                # 3. 紐付け (勤務地 vs 時程表)
                integrated_data = p0.data_integration(pdf_dic, time_dic)
                
                # 4. CSV行生成
                target_date_str = target_date.strftime("%Y-%m-%d")
                # PDFの列：1日が index 1 になるように設定
                current_col = target_date.day 
                
                final_rows = p0.process_integrated_data(integrated_data, target_date_str, current_col)
                
                if final_rows:
                    columns = ["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location"]
                    df_final = pd.DataFrame(final_rows, columns=columns)
                    
                    # プレビュー表示
                    st.success(f"「{target_staff}」のシフトを正常に抽出しました。")
                    st.markdown("### 📅 CSVプレビュー")
                    st.dataframe(df_final)
                    
                    # ダウンロード準備
                    csv_buffer = io.StringIO()
                    df_final.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
                    
                    st.download_button(
                        label="月間.csv をダウンロード",
                        data=csv_buffer.getvalue(),
                        file_name=f"月間_{target_staff}_{target_date_str}.csv",
                        mime="text/csv",
                    )
                else:
                    st.warning(f"{target_date_str} のシフトデータが見つかりませんでした。")
            else:
                st.error(f"PDF内に「{target_staff}」が見つかりませんでした。")
        else:
            st.info("サイドバーの「解析を実行する」ボタンを押してください。")
    else:
        st.info("解析を行うにはPDFファイルをアップロードしてください。")

if __name__ == "__main__":
    main()
