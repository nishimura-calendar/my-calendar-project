import streamlit as st
import pandas as pd
import io
import practice_0 as p0

def main():
    st.set_page_config(page_title="カレンダー作成ツール", layout="centered")
    
    # セッション状態で年月と名前を保持
    if 'pdf_year' not in st.session_state: st.session_state.pdf_year = None
    if 'pdf_month' not in st.session_state: st.session_state.pdf_month = None
    if 'staff_name' not in st.session_state: st.session_state.staff_name = "西村 文宏"

    st.title("📅 勤務スケジュール抽出システム")
    st.markdown("PDFのシフト表からGoogleカレンダー用CSVを生成します。")

    # --- 基本設定 ---
    st.subheader("1. 基本設定")
    col_name, col_sheet = st.columns([1, 1])
    with col_name:
        target_staff = st.text_input("あなたの名前", value=st.session_state.staff_name)
        st.session_state.staff_name = target_staff
    with col_sheet:
        sheet_id = st.text_input("時程表スプレッドシートID", value="1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE")

    # --- PDFアップロード ---
    st.subheader("2. ファイルのアップロード")
    pdf_file = st.file_uploader("シフト表（PDF）を選択してください", type="pdf")

    if pdf_file:
        pdf_bytes = pdf_file.read()
        pdf_stream = io.BytesIO(pdf_bytes)
        
        # PDFから年月情報を抽出（表示用＆計算用）
        extracted_y, extracted_m = p0.extract_year_month_from_pdf(pdf_stream)
        
        if extracted_y and extracted_m:
            st.session_state.pdf_year = extracted_y
            st.session_state.pdf_month = extracted_m
            st.success(f"📁 ファイル名: {pdf_file.name} を受理しました。")
            st.info(f"📅 解析対象年月: **{extracted_y}年 {extracted_m}月**")
        else:
            st.error("PDFから年月の取得ができませんでした。PDFの形式を確認してください。")

        # 実行ボタン
        if st.session_state.pdf_year and st.session_state.pdf_month:
            if st.button("🚀 実行してカレンダーを生成", use_container_width=True, type="primary"):
                try:
                    service = p0.get_gdrive_service(st.secrets)
                    
                    # 1. 時程表の取得
                    with st.spinner("時程表を読み込んでいます..."):
                        time_dic = p0.time_schedule_from_drive(service, sheet_id)
                    
                    # 2. PDF解析
                    with st.spinner(f"PDFから {target_staff} さんの勤務を解析中..."):
                        pdf_stream.seek(0)
                        pdf_dic = p0.pdf_reader(pdf_stream, target_staff)
                    
                    if not pdf_dic:
                        st.error(f"PDF内に『{target_staff}』が見つかりませんでした。")
                        return

                    # 3. データの紐付け
                    integrated_dic, logs = p0.data_integration(pdf_dic, time_dic)

                    # 4. カレンダー行の生成
                    with st.spinner("スケジュールを計算中..."):
                        final_rows = p0.process_full_month(
                            integrated_dic, 
                            int(st.session_state.pdf_year), 
                            int(st.session_state.pdf_month)
                        )

                    if final_rows:
                        st.subheader("3. 生成結果の確認")
                        df_res = pd.DataFrame(final_rows, columns=[
                            "Subject", "Start Date", "Start Time", "End Date", "End Time", 
                            "All Day Event", "Description", "Location"
                        ])
                        
                        st.dataframe(df_res, use_container_width=True)

                        csv_buffer = io.StringIO()
                        df_res.to_csv(csv_buffer, index=False, encoding="utf_8_sig")
                        
                        st.download_button(
                            label="📥 Googleカレンダー用CSVをダウンロード",
                            data=csv_buffer.getvalue(),
                            file_name=f"schedule_{st.session_state.pdf_year}{st.session_state.pdf_month:02d}_{target_staff}.csv",
                            mime="text/csv",
                            use_container_width=True
                        )
                except Exception as e:
                    st.error(f"エラーが発生しました。時程表の空欄（NaN）または形式を確認してください。")
                    with st.expander("詳細なエラー内容"):
                        st.exception(e)
    else:
        st.session_state.pdf_year = None
        st.session_state.pdf_month = None

if __name__ == "__main__":
    main()
