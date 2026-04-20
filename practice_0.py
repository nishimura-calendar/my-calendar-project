import streamlit as st
import pandas as pd
import io
import practice_0 as p0
import datetime
import calendar

def main():
    st.set_page_config(page_title="勤務スケジュール抽出", layout="wide")
    
    if 'staff_name' not in st.session_state: 
        st.session_state.staff_name = "西村 文宏"

    st.title("📅 勤務スケジュール抽出システム")
    st.markdown("PDFのシフト表からGoogleカレンダー用CSVを自動生成します。")

    st.subheader("1. 基本設定")
    col_name, col_sheet = st.columns([1, 1])
    with col_name:
        target_staff = st.text_input("あなたの名前", value=st.session_state.staff_name)
        st.session_state.staff_name = target_staff
    with col_sheet:
        sheet_id = st.text_input("時程表スプレッドシートID", value="1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE")

    st.subheader("2. ファイルのアップロード")
    pdf_file = st.file_uploader("シフト表（PDF）を選択してください", type="pdf")

    if pdf_file and target_staff:
        pdf_file.seek(0)
        pdf_bytes = pdf_file.read()
        pdf_stream = io.BytesIO(pdf_bytes)
        
        # ファイル名または中身から年月を取得
        apply_y, apply_m = p0.extract_year_month_from_text(pdf_file.name)
        
        # もしファイル名から取れなければPDFの中身から再試行
        if not apply_y or not apply_m:
            with st.spinner("PDF内から年月を特定中..."):
                apply_y, apply_m = p0.identify_date_from_content(pdf_stream)

        if apply_y and apply_m:
            try:
                service = p0.get_gdrive_service(st.secrets)
                with st.spinner(f"解析を実行中 ({apply_y}年{apply_m}月)..."):
                    # 時程表の取得
                    time_dic = p0.time_schedule_from_drive(service, sheet_id)
                    
                    pdf_stream.seek(0)
                    # pdf_readerは (解析データ辞書, year, month) を返す
                    pdf_dic, detected_y, detected_m = p0.pdf_reader(pdf_stream, target_staff)
                    
                    # 警告チェック（日数の不一致など）
                    expected_days = calendar.monthrange(apply_y, apply_m)[1]
                    
                    if not pdf_dic:
                        st.error(f"PDF内に『{target_staff}』が見つかりませんでした。")
                        st.info("ターゲット名の入力（姓名の間のスペース等）がPDFと一致しているか確認してください。")
                    else:
                        # データ統合とスケジュール生成
                        integrated_dic, _ = p0.data_integration(pdf_dic, time_dic)
                        final_rows = p0.process_full_month(integrated_dic, int(apply_y), int(apply_m))

                        if final_rows:
                            st.success(f"✅ {apply_y}年{apply_m}月のスケジュールを生成しました。")
                            df_res = pd.DataFrame(final_rows, columns=["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location"])
                            
                            st.subheader("抽出結果のプレビュー")
                            st.dataframe(df_res, use_container_width=True)
                            
                            csv_buffer = io.StringIO()
                            df_res.to_csv(csv_buffer, index=False, encoding="utf_8_sig")
                            st.download_button(
                                label="📥 この内容でカレンダー用CSVをダウンロード",
                                data=csv_buffer.getvalue(),
                                file_name=f"schedule_{apply_y}{apply_m:02d}_{target_staff}.csv",
                                mime="text/csv",
                                use_container_width=True,
                                type="primary"
                            )
                        else:
                            st.warning("スケジュールを生成できませんでした。名前の行にシフト記号が入っているか確認してください。")
            except Exception as e:
                st.error(f"解析中にエラーが発生しました: {e}")
                st.exception(e) # デバッグ用に詳細表示
        else:
            st.error("年月を特定できません。ファイル名に『1月』等の情報を含めるか、PDF内の日付表記を確認してください。")

if __name__ == "__main__":
    main()
