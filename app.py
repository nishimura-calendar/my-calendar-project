import streamlit as st
import pandas as pd
import io
import practice_0 as p0
import datetime
import calendar
import pdfplumber

def main():
    st.set_page_config(page_title="勤務スケジュール抽出", layout="centered")
    
    if 'staff_name' not in st.session_state: 
        st.session_state.staff_name = "西村 文宏"

    st.title("📅 勤務スケジュール抽出システム")
    st.markdown("PDFのシフト表からGoogleカレンダー用CSVを生成します。")

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
        pdf_bytes = pdf_file.read()
        pdf_stream = io.BytesIO(pdf_bytes)
        
        # 1. ファイル名から年月を抽出（これが「正」）
        apply_y, apply_m = p0.extract_year_month_from_text(pdf_file.name)
        
        if apply_y and apply_m:
            # 2. 整合性チェック
            mismatch_reasons = []
            
            # (A) 月末日のチェック
            expected_days = calendar.monthrange(apply_y, apply_m)[1]
            actual_max_day = p0.extract_max_day_from_pdf(pdf_stream)
            if actual_max_day and actual_max_day != expected_days:
                mismatch_reasons.append(f"日数の不一致: {apply_m}月は{expected_days}日までですが、PDFは{actual_max_day}日まであります。")
            
            # (B) 1日の曜日のチェック
            first_day_date = datetime.date(apply_y, apply_m, 1)
            wd_list = ["月", "火", "水", "木", "金", "土", "日"]
            expected_wd = wd_list[first_day_date.weekday()]
            actual_wd = p0.extract_first_weekday_from_pdf(pdf_stream)
            if actual_wd and actual_wd != expected_wd:
                mismatch_reasons.append(f"曜日の不一致: {apply_y}年{apply_m}月1日は({expected_wd})曜日ですが、PDFは({actual_wd})曜日となっています。")

            # --- 判定と表示 ---
            if mismatch_reasons:
                st.error("⚠️ ファイル名とPDFの内容に相違が見つかりました")
                for reason in mismatch_reasons:
                    st.write(f"- {reason}")
                
                with st.expander("アップロードされたPDFの内容を確認する", expanded=True):
                    try:
                        pdf_stream.seek(0)
                        with pdfplumber.open(pdf_stream) as pdf:
                            for i, page in enumerate(pdf.pages):
                                img = page.to_image(resolution=100)
                                st.image(img.original, use_container_width=True, caption=f"PDF {i+1}ページ")
                    except Exception as e:
                        st.error(f"プレビュー表示エラー: {e}")
            else:
                st.success(f"✅ 整合性確認済み: {apply_y}年{apply_m}月として処理します。")

            # 3. 実行ボタン
            if st.button("🚀 実行してカレンダーを生成", use_container_width=True, type="primary"):
                try:
                    service = p0.get_gdrive_service(st.secrets)
                    with st.spinner("解析中..."):
                        time_dic = p0.time_schedule_from_drive(service, sheet_id)
                        pdf_stream.seek(0)
                        pdf_dic = p0.pdf_reader(pdf_stream, target_staff)
                        
                        if not pdf_dic:
                            st.error(f"PDF内に『{target_staff}』が見つかりませんでした。")
                        else:
                            integrated_dic, _ = p0.data_integration(pdf_dic, time_dic)
                            final_rows = p0.process_full_month(integrated_dic, int(apply_y), int(apply_m))

                            if final_rows:
                                st.subheader("3. 生成結果の確認")
                                df_res = pd.DataFrame(final_rows, columns=["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location"])
                                st.dataframe(df_res, use_container_width=True)
                                
                                csv_buffer = io.StringIO()
                                df_res.to_csv(csv_buffer, index=False, encoding="utf_8_sig")
                                st.download_button(
                                    label="📥 CSVをダウンロード",
                                    data=csv_buffer.getvalue(),
                                    file_name=f"schedule_{apply_y}{apply_m:02d}_{target_staff}.csv",
                                    mime="text/csv",
                                    use_container_width=True
                                )
                            else:
                                st.warning("該当するシフトが見つかりませんでした。")
                except Exception as e:
                    st.error(f"エラーが発生しました: {e}")
        else:
            st.error("ファイル名から年月（例: 26(1)）を特定できませんでした。")

if __name__ == "__main__":
    main()
