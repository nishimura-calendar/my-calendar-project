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
    
    # 基本事項：スプレッドシートID
    sheet_id = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

    # --- ファイルアップロード ---
    st.subheader("📁 勤務表PDFのアップロード")
    uploaded_pdf = st.file_uploader("勤務表PDFを選択してください", type="pdf")

    # --- 解析実行ボタン ---
    analyze_button = st.sidebar.button("解析を実行する", type="primary")

    if uploaded_pdf:
        if analyze_button:
            # 1. 時程表の取得
            with st.spinner("Google Driveから時程表を取得中..."):
                try:
                    service = p0.get_gdrive_service(st.secrets)
                    time_dic = p0.time_schedule_from_drive(service, sheet_id)
                    if not time_dic:
                        st.warning("時程表データが見つかりませんでした。")
                        return
                except Exception as e:
                    st.error(f"時程表取得エラー: {e}")
                    return

            # 2. PDF解析
            with st.spinner("PDFを解析中..."):
                pdf_dic = p0.pdf_reader(uploaded_pdf, target_staff)
            
            if pdf_dic:
                # 3. 紐付け (紐付け結果のログを表示)
                integrated_data, debug_logs = p0.data_integration(pdf_dic, time_dic)
                
                with st.expander("🔍 勤務地の紐付けログを確認"):
                    for log in debug_logs:
                        st.write(log)
                
                if not integrated_data:
                    st.error("PDFで見つかった勤務地が、時程表のシート名と一致しませんでした。ログを確認してください。")
                    return

                # 4. 全日程のCSV行生成
                with st.spinner("全日程のシフトを抽出中..."):
                    # PDFから年月の推定（※本来はPDF内から取得。一旦実行時の年月を使用）
                    now = datetime.now()
                    current_year = now.year
                    current_month = now.month
                    
                    all_month_rows = p0.process_full_month(integrated_data, current_year, current_month)
                
                if all_month_rows:
                    columns = ["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location"]
                    df_final = pd.DataFrame(all_month_rows, columns=columns)
                    
                    st.success(f"「{target_staff}」の全日程シフトを抽出しました。")
                    st.markdown("### 📅 CSVプレビュー (全日程)")
                    st.dataframe(df_final)
                    
                    csv_buffer = io.StringIO()
                    df_final.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
                    
                    st.download_button(
                        label="月間.csv をダウンロード",
                        data=csv_buffer.getvalue(),
                        file_name=f"月間_{target_staff}_{current_year}{current_month:02d}.csv",
                        mime="text/csv",
                    )
                else:
                    st.warning("シフトデータが抽出されませんでした。")
            else:
                st.error(f"PDF内に「{target_staff}」が見つかりませんでした。名前が正しいか、PDFの形式を確認してください。")
        else:
            st.info("サイドバーの「解析を実行する」ボタンを押してください。")
    else:
        st.info("解析を行うにはPDFファイルをアップロードしてください。")

if __name__ == "__main__":
    main()
