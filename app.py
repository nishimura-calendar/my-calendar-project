import streamlit as st
import pandas as pd
import io
import practice_0 as p0
import datetime
import calendar

def main():
    st.set_page_config(page_title="勤務スケジュール抽出", layout="centered")
    
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

    if pdf_file:
        pdf_file.seek(0)
        pdf_bytes = pdf_file.read()
        pdf_stream = io.BytesIO(pdf_bytes)
        
        # ファイル名から年月を取得
        apply_y, apply_m = p0.extract_year_month_from_text(pdf_file.name)
        
        if apply_y and apply_m:
            mismatch_warnings = []
            
            with st.spinner("PDFの整合性をチェック中..."):
                # 月末日のチェック
                expected_days = calendar.monthrange(apply_y, apply_m)[1]
                actual_max_day = p0.extract_max_day_from_pdf(pdf_stream)
                if actual_max_day and actual_max_day != expected_days:
                    mismatch_warnings.append(f"【日数の不一致】{apply_m}月は{expected_days}日までですが、PDF内には{actual_max_day}日までのデータが見つかりました。")
                
                # 曜日のチェック
                first_day_date = datetime.date(apply_y, apply_m, 1)
                wd_list = ["月", "火", "水", "木", "金", "土", "日"]
                expected_wd = wd_list[first_day_date.weekday()]
                pdf_stream.seek(0)
                actual_wd = p0.extract_first_weekday_from_pdf(pdf_stream)
                
                if actual_wd and actual_wd != expected_wd:
                    mismatch_warnings.append(f"【曜日の不一致】ファイル名では{apply_y}年{apply_m}月（1日は{expected_wd}曜日）ですが、PDF内では1日が{actual_wd}曜日となっています。")

            # 警告がある場合の表示
            if mismatch_warnings:
                with st.expander("⚠️ 整合性に関する警告があります。内容を確認してください", expanded=True):
                    for msg in mismatch_warnings:
                        st.warning(msg)
                    st.info("※PDFのレイアウトやファイル名の年表記により誤判定される場合があります。以下の抽出結果が正しいか確認してください。")

            # 解析実行
            try:
                service = p0.get_gdrive_service(st.secrets)
                with st.spinner(f"シフト解析を実行中..."):
                    time_dic = p0.time_schedule_from_drive(service, sheet_id)
                    pdf_stream.seek(0)
                    pdf_dic = p0.pdf_reader(pdf_stream, target_staff)
                    
                    if not pdf_dic:
                        st.error(f"PDF内に『{target_staff}』が見つかりませんでした。名前の表記がPDFと一致しているか確認してください。")
                    else:
                        integrated_dic, _ = p0.data_integration(pdf_dic, time_dic)
                        # 警告があっても、ユーザーが確認できるように結果を生成して表示する
                        final_rows = p0.process_full_month(integrated_dic, int(apply_y), int(apply_m))

                        if final_rows:
                            st.success(f"✅ スケジュールを抽出しました。")
                            df_res = pd.DataFrame(final_rows, columns=["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location"])
                            
                            # ここで抽出された表を必ず表示する
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
                            st.warning("スケジュール項目を抽出できませんでした。名前の行にシフト記号が入っているか確認してください。")
            except Exception as e:
                st.error(f"解析中に技術的なエラーが発生しました: {e}")
        else:
            st.error(f"ファイル名『{pdf_file.name}』から対象となる年月（例：2026年1月）を特定できません。ファイル名に年月を含めてください。")

if __name__ == "__main__":
    main()
