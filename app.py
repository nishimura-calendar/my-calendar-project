import streamlit as st
import pandas as pd
import io
import practice_0 as p0

def main():
    st.set_page_config(page_title="カレンダー作成ツール", layout="wide")
    
    # セッション状態で年月を保持
    if 'pdf_year' not in st.session_state: st.session_state.pdf_year = 2024
    if 'pdf_month' not in st.session_state: st.session_state.pdf_month = 4

    with st.sidebar:
        st.header("📋 設定")
        target_staff = st.text_input("あなたの名前", value="西村 文宏")
        
        st.subheader("対象年月")
        col_y, col_m = st.columns(2)
        target_year = col_y.number_input("年", min_value=2024, value=st.session_state.pdf_year)
        target_month = col_m.number_input("月", min_value=1, max_value=12, value=st.session_state.pdf_month)
        
        sheet_id = st.text_input("時程表 ID", value="1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE")

    st.title("📅 勤務スケジュール抽出")

    pdf_file = st.file_uploader("1. シフト表PDFをアップロード", type="pdf")

    if pdf_file:
        # PDFを読み込み年月抽出を試みる
        pdf_bytes = pdf_file.read()
        pdf_stream = io.BytesIO(pdf_bytes)
        extracted_y, extracted_m = p0.extract_year_month_from_pdf(pdf_stream)
        
        # 抽出成功かつ現在のセッションと異なる場合は更新
        if extracted_y and (extracted_y != st.session_state.pdf_year or extracted_m != st.session_state.pdf_month):
            st.session_state.pdf_year = extracted_y
            st.session_state.pdf_month = extracted_m
            st.info(f"PDFから「{extracted_y}年{extracted_m}月」を検出しました。")
            st.rerun()

        if sheet_id:
            if st.button("🚀 実行する"):
                try:
                    service = p0.get_gdrive_service(st.secrets)
                    
                    # 時程表の取得
                    with st.spinner("Google Driveから時程表を取得中..."):
                        time_dic = p0.time_schedule_from_drive(service, sheet_id)
                    
                    if time_dic:
                        with st.expander("📊 取得した勤務地別時程表を確認"):
                            tabs = st.tabs(list(time_dic.keys()))
                            for tab, (place, df) in zip(tabs, time_dic.items()):
                                with tab:
                                    st.dataframe(df, use_container_width=True)

                    # PDF解析
                    with st.spinner("PDFから勤務データを抽出中..."):
                        # 解析用にストリームをリセット
                        pdf_stream.seek(0)
                        pdf_dic = p0.pdf_reader(pdf_stream, target_staff)
                    
                    if not pdf_dic:
                        st.error(f"PDF内に『{target_staff}』が見つかりませんでした。")
                        return

                    # 紐付け
                    st.subheader("2. 紐付け結果")
                    integrated_dic, logs = p0.data_integration(pdf_dic, time_dic)
                    st.table(pd.DataFrame(logs))

                    # カレンダー生成
                    with st.spinner("詳細スケジュールを計算中..."):
                        final_rows = p0.process_full_month(integrated_dic, int(target_year), int(target_month))

                    if final_rows:
                        st.subheader("3. 生成結果プレビュー")
                        df_res = pd.DataFrame(final_rows, columns=["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location"])
                        st.dataframe(df_res, use_container_width=True)

                        csv_buffer = io.StringIO()
                        df_res.to_csv(csv_buffer, index=False, encoding="utf_8_sig")
                        st.download_button(
                            label="📥 Googleカレンダー用CSVを保存",
                            data=csv_buffer.getvalue(),
                            file_name=f"schedule_{target_staff}_{target_year}{target_month:02d}.csv",
                            mime="text/csv"
                        )
                
                except Exception as e:
                    st.error(f"エラーが発生しました: {e}")
                    st.exception(e)

if __name__ == "__main__":
    main()
