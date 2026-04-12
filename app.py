import streamlit as st
import pandas as pd
import io
import datetime
from practice_0 import (
    get_gdrive_service,
    time_schedule_from_drive,
    pdf_reader,
    data_integration,
    process_full_month
)

# --- 設定 ---
# ※ secrets.toml または Streamlit Cloud の Secrets に設定が必要です
# target_staff = "西村 文宏"
# year = 2024
# month = 4

def main():
    st.title("勤務スケジュール抽出システム")
    st.sidebar.header("設定")

    # 1. 入力パラメータ
    target_staff = st.sidebar.text_input("対象スタッフ名", value="西村 文宏")
    target_year = st.sidebar.number_input("対象年", min_value=2020, max_value=2030, value=2024)
    target_month = st.sidebar.number_input("対象月", min_value=1, max_value=12, value=4)
    
    # 2. ファイルアップロード
    pdf_file = st.file_uploader("勤務表PDFをアップロード", type="pdf")
    
    # 時程表（Google Drive上のIDを指定、またはファイルアップロード）
    # 今回はID指定を想定していますが、アップロード形式も可能です
    g_sheet_id = st.sidebar.text_input("時程表 Google Sheet ID", help="URLの /d/.../edit の部分")

    if pdf_file and g_sheet_id:
        if st.button("スケジュール生成開始"):
            try:
                # Google Drive サービス取得
                # secrets に "gcp_service_account" が設定されている前提
                service = get_gdrive_service(st.secrets)
                
                with st.spinner("時程表を読み込み中..."):
                    # 時程表を「シート内の勤務地ブロック」として取得
                    time_dic = time_schedule_from_drive(service, g_sheet_id)
                
                if not time_dic:
                    st.error("時程表の読み込みに失敗しました。")
                    return

                with st.spinner("PDFを解析中..."):
                    # PDFから対象スタッフのデータを抽出
                    pdf_stream = io.BytesIO(pdf_file.read())
                    pdf_dic = pdf_reader(pdf_stream, target_staff)
                
                if not pdf_dic:
                    st.error(f"PDFから『{target_staff}』が見つかりませんでした。")
                    return

                # データ紐付け（'C' -> 'T2' などの救済を含む）
                integrated_dic, logs = data_integration(pdf_dic, time_dic)
                
                # ログの表示
                for log in logs:
                    if "✅" in log:
                        st.success(log)
                    else:
                        st.warning(log)

                if not integrated_dic:
                    st.error("時程表とPDFの勤務地を紐付けられませんでした。")
                    return

                with st.spinner("詳細スケジュールを算出中..."):
                    # 全日程の行を生成
                    final_rows = process_full_month(integrated_dic, int(target_year), int(target_month))

                if final_rows:
                    # 結果の表示とCSVダウンロード
                    df_result = pd.DataFrame(
                        final_rows,
                        columns=["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location"]
                    )
                    
                    st.subheader("生成されたスケジュール（プレビュー）")
                    st.dataframe(df_result)

                    # CSVダウンロード
                    csv_buffer = io.StringIO()
                    df_result.to_csv(csv_buffer, index=False, encoding="utf_8_sig")
                    st.download_button(
                        label="Googleカレンダー用CSVをダウンロード",
                        data=csv_buffer.getvalue(),
                        file_name=f"schedule_{target_staff}_{target_year}{target_month:02d}.csv",
                        mime="text/csv"
                    )
                else:
                    st.warning("該当するシフトデータが見つかりませんでした。")

            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
                st.exception(e)

if __name__ == "__main__":
    main()
