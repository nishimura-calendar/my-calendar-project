import streamlit as st
import pandas as pd
import io
from practice_0 import (
    get_gdrive_service,
    time_schedule_from_drive,
    pdf_reader,
    data_integration,
    process_full_month
)

def main():
    st.set_page_config(page_title="勤務スケジュール抽出", layout="wide")
    st.title("📅 勤務スケジュール抽出システム")

    # サイドバー：設定
    st.sidebar.header("📋 設定")
    target_staff = st.sidebar.text_input("対象スタッフ名", value="西村 文宏")
    target_year = st.sidebar.number_input("対象年", min_value=2020, max_value=2030, value=2024)
    target_month = st.sidebar.number_input("対象月", min_value=1, max_value=12, value=4)
    g_sheet_id = st.sidebar.text_input("時程表 Google Sheet ID")

    # メイン：ファイルアップロード
    st.subheader("1. 勤務表PDFのアップロード")
    pdf_file = st.file_uploader("PDFファイルを選択してください", type="pdf")

    if pdf_file and g_sheet_id:
        if st.button("紐付けを確認して実行"):
            try:
                service = get_gdrive_service(st.secrets)
                
                # 1. 時程表の読み込み
                with st.spinner("時程表を読み込み中..."):
                    time_dic = time_schedule_from_drive(service, g_sheet_id)
                
                if not time_dic:
                    st.error("時程表の読み込みに失敗しました。IDとアクセス権限を確認してください。")
                    return

                # 2. PDFの解析
                with st.spinner("PDFからスタッフを検索中..."):
                    pdf_file.seek(0)
                    pdf_stream = io.BytesIO(pdf_file.read())
                    pdf_dic = pdf_reader(pdf_stream, target_staff)
                
                if not pdf_dic:
                    st.error(f"PDFから『{target_staff}』が見つかりませんでした。")
                    return

                # 3. 紐付け確認
                st.subheader("2. 紐付けの確認")
                integrated_dic, logs = data_integration(pdf_dic, time_dic)
                
                # 紐付け結果をテーブルで表示
                log_df = pd.DataFrame(logs)
                st.table(log_df)

                if not integrated_dic:
                    st.error("紐付けに失敗したため、スケジュールを生成できません。")
                    return

                # 4. スケジュール生成
                with st.spinner("全日程を解析してCSVを作成中..."):
                    final_rows = process_full_month(integrated_dic, int(target_year), int(target_month))

                if final_rows:
                    st.subheader("3. 生成結果")
                    df_result = pd.DataFrame(
                        final_rows,
                        columns=["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location"]
                    )
                    
                    st.success(f"{len(df_result)} 件の予定を抽出しました。")
                    st.dataframe(df_result, use_container_width=True)

                    # CSVダウンロード
                    csv_buffer = io.StringIO()
                    df_result.to_csv(csv_buffer, index=False, encoding="utf_8_sig")
                    st.download_button(
                        label="Googleカレンダー用CSVを保存",
                        data=csv_buffer.getvalue(),
                        file_name=f"schedule_{target_staff}_{target_year}{target_month:02d}.csv",
                        mime="text/csv"
                    )
                else:
                    st.warning("該当するシフトデータが見つかりませんでした。")

            except Exception as e:
                st.error(f"実行エラー: {e}")

if __name__ == "__main__":
    main()
