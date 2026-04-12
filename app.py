import streamlit as st
import pandas as pd
import io
import practice_0 as p0

def main():
    st.set_page_config(page_title="カレンダー作成ツール", layout="wide")
    
    # --- サイドバー設定 ---
    with st.sidebar:
        st.header("📋 設定")
        target_staff = st.text_input("あなたの名前を入力（例: 西村 文宏）", value="西村 文宏")
        col_y, col_m = st.columns(2)
        target_year = col_y.number_input("年", min_value=2024, value=2024)
        target_month = col_m.number_input("月", min_value=1, max_value=12, value=4)
        
        # 時程表ID（xlsxとして読み込む）
        sheet_id = st.text_input("時程表 ID", value="1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE")

    st.title("📅 勤務スケジュール抽出")

    # 1. PDFアップロード
    st.subheader("1. シフト表PDFをアップロード")
    pdf_file = st.file_uploader("PDFファイルを選択", type="pdf")

    if pdf_file and sheet_id:
        if st.button("🚀 実行する"):
            try:
                service = p0.get_gdrive_service(st.secrets)
                
                # 時程表読み込み（常にExcelとして処理）
                with st.spinner("Google Driveから時程表（Excel）を取得中..."):
                    time_dic = p0.time_schedule_from_drive(service, sheet_id)
                
                # PDF解析
                with st.spinner("PDFから勤務行を抽出中..."):
                    pdf_file.seek(0)
                    pdf_stream = io.BytesIO(pdf_file.read())
                    pdf_dic = p0.pdf_reader(pdf_stream, target_staff)
                
                if not pdf_dic:
                    st.error(f"PDF内に『{target_staff}』が見つかりませんでした。名前のスペース等を確認してください。")
                    return

                # 紐付け
                st.subheader("2. 紐付け結果")
                integrated_dic, logs = p0.data_integration(pdf_dic, time_dic)
                st.table(pd.DataFrame(logs))

                if not integrated_dic:
                    st.error("有効な紐付けがありませんでした。場所名を確認してください。")
                    return

                # スケジュール計算
                with st.spinner("1ヶ月分の詳細スケジュールを計算中..."):
                    final_rows = p0.process_full_month(integrated_dic, int(target_year), int(target_month))

                if final_rows:
                    st.subheader("3. 生成結果プレビュー")
                    df_res = pd.DataFrame(final_rows, columns=["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location"])
                    st.dataframe(df_res, use_container_width=True)

                    # CSV出力
                    csv_buffer = io.StringIO()
                    df_res.to_csv(csv_buffer, index=False, encoding="utf_8_sig")
                    st.download_button(
                        label="📥 Googleカレンダー用CSVを保存",
                        data=csv_buffer.getvalue(),
                        file_name=f"schedule_{target_staff}_{target_year}{target_month:02d}.csv",
                        mime="text/csv"
                    )
                else:
                    st.warning("スケジュールが1件も生成されませんでした。")

            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
                st.exception(e)
    else:
        st.info("名前、年・月、時程表IDをサイドバーで確認し、PDFをアップロードしてください。")

if __name__ == "__main__":
    main()
