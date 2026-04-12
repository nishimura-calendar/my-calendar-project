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
    st.set_page_config(page_title="勤務スケジュール抽出システム", layout="wide")
    
    # --- サイドバー：設定エリア ---
    with st.sidebar:
        st.header("📋 設定")
        target_staff = st.text_input("対象スタッフ名", value="西村 文宏")
        
        col_year, col_month = st.columns(2)
        with col_year:
            target_year = st.number_input("対象年", min_value=2020, max_value=2030, value=2024)
        with col_month:
            target_month = st.number_input("対象月", min_value=1, max_value=12, value=4)
        
        g_sheet_id = st.text_input("時程表 Google Sheet ID", value="")
        st.caption("※Google Drive上のIDを入力してください")

    # --- メインエリア ---
    st.title("📅 勤務スケジュール抽出")
    st.markdown("PDFの勤務表を読み込み、Googleカレンダー用CSVを生成します。")

    # 1. PDFのアップロード
    st.subheader("1. 勤務表PDFのアップロード")
    pdf_file = st.file_uploader("PDFファイルを選択（複数ページ対応）", type="pdf")

    if pdf_file and g_sheet_id:
        st.info("解析準備が整いました。下のボタンを押して紐付けを確認してください。")
        
        if st.button("🚀 紐付けを確認してスケジュール生成"):
            try:
                # 認証
                service = get_gdrive_service(st.secrets)
                
                # 時程表読み込み
                with st.spinner("Google Driveから時程表を取得中..."):
                    time_dic = time_schedule_from_drive(service, g_sheet_id)
                
                if not time_dic:
                    st.error("時程表の取得に失敗しました。IDが正しいか確認してください。")
                    return

                # PDF解析
                with st.spinner("PDFを解析中..."):
                    pdf_file.seek(0)
                    pdf_stream = io.BytesIO(pdf_file.read())
                    pdf_dic = pdf_reader(pdf_stream, target_staff)
                
                if not pdf_dic:
                    st.error(f"PDF内に『{target_staff}』が見つかりませんでした。")
                    return

                # 紐付け確認表示
                st.subheader("2. 勤務地の紐付け確認")
                integrated_dic, logs = data_integration(pdf_dic, time_dic)
                
                # ログをテーブルで表示
                log_df = pd.DataFrame(logs)
                st.table(log_df)

                if not integrated_dic:
                    st.error("有効な紐付けがありません。勤務地名を確認してください。")
                    return

                # スケジュール計算
                with st.spinner("詳細スケジュール（交代相手含む）を算定中..."):
                    final_rows = process_full_month(integrated_dic, int(target_year), int(target_month))

                if final_rows:
                    st.subheader("3. 生成されたスケジュール")
                    df_result = pd.DataFrame(
                        final_rows,
                        columns=["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location"]
                    )
                    
                    st.success(f"{len(df_result)} 件の予定を抽出しました。")
                    st.dataframe(df_result, use_container_width=True)

                    # ダウンロード
                    csv_buffer = io.StringIO()
                    df_result.to_csv(csv_buffer, index=False, encoding="utf_8_sig")
                    st.download_button(
                        label="📥 Googleカレンダー用CSVをダウンロード",
                        data=csv_buffer.getvalue(),
                        file_name=f"schedule_{target_staff}_{target_year}{target_month:02d}.csv",
                        mime="text/csv"
                    )
                else:
                    st.warning("指定されたシフト記号に基づく時間データが見つかりませんでした。")

            except Exception as e:
                st.error(f"システムエラーが発生しました: {e}")
    
    else:
        st.info("左側のサイドバーで設定を入力し、PDFファイルをアップロードしてください。")

if __name__ == "__main__":
    main()
