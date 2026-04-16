import streamlit as st
import pandas as pd
import io
import practice_0 as p0
import pdfplumber
import datetime

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
        
        # 1. ファイル名から年月を抽出 (最優先の「正」とする)
        fname_y, fname_m = p0.extract_year_month_from_text(pdf_file.name)
        # 2. PDF内部テキストから年月を抽出
        pdf_y, pdf_m = p0.extract_year_month_from_pdf(pdf_stream)
        
        # ファイル名の情報をセッションにセット
        st.session_state.pdf_year = fname_y if fname_y else pdf_y
        st.session_state.pdf_month = fname_m if fname_m else pdf_m
        
        # --- 相違チェック ---
        mismatch_reason = []
        
        # (a) 年月の相違チェック
        if fname_y and pdf_y and (fname_y != pdf_y or fname_m != pdf_m):
            mismatch_reason.append(f"ファイル名({fname_y}/{fname_m})と内部テキスト({pdf_y}/{pdf_m})が一致しません。")

        # (b) 曜日の相違チェック
        # ファイル名由来の年月の1日の曜日を取得
        if st.session_state.pdf_year and st.session_state.pdf_month:
            first_day = datetime.date(st.session_state.pdf_year, st.session_state.pdf_month, 1)
            weekdays = ["月", "火", "水", "木", "金", "土", "日"]
            expected_wd = weekdays[first_day.weekday()]
            
            # PDFから1日の曜日を読み取る (practice_0内で解析)
            actual_wd = p0.extract_first_weekday_from_pdf(pdf_stream)
            
            if actual_wd and actual_wd != expected_wd:
                mismatch_reason.append(f"カレンダー上の1日({expected_wd}曜)とPDF記載の曜日({actual_wd}曜)が一致しません。")

        # 警告表示とPDF表示の判定
        if mismatch_reason:
            st.warning("⚠️ 検索名とファイルの内容に違いが認められる。")
            for reason in mismatch_reason:
                st.write(f"- {reason}")
            
            # 不一致時は自動でPDFを表示
            st.info("PDFの内容を確認してください:")
            try:
                pdf_stream.seek(0)
                with pdfplumber.open(pdf_stream) as pdf:
                    for i, page in enumerate(pdf.pages):
                        img = page.to_image(resolution=150)
                        st.image(img.original, use_container_width=True, caption=f"PDF {i+1}ページ目")
            except Exception as e:
                st.error(f"プレビュー表示エラー: {e}")
        else:
            st.success(f"📁 {pdf_file.name} を受理しました。")
            with st.expander("📄 PDFプレビューを表示"):
                try:
                    pdf_stream.seek(0)
                    with pdfplumber.open(pdf_stream) as pdf:
                        for i, page in enumerate(pdf.pages):
                            img = page.to_image(resolution=150)
                            st.image(img.original, use_container_width=True)
                except Exception:
                    pass

        # 実行ボタン
        if st.session_state.pdf_year and st.session_state.pdf_month:
            if st.button("🚀 実行してカレンダーを生成", use_container_width=True, type="primary"):
                try:
                    service = p0.get_gdrive_service(st.secrets)
                    with st.spinner("解析中..."):
                        time_dic = p0.time_schedule_from_drive(service, sheet_id)
                        pdf_stream.seek(0)
                        pdf_dic = p0.pdf_reader(pdf_stream, target_staff)
                        
                        if not pdf_dic:
                            st.error(f"PDF内に『{target_staff}』が見つかりませんでした。")
                            return

                        integrated_dic, _ = p0.data_integration(pdf_dic, time_dic)
                        final_rows = p0.process_full_month(
                            integrated_dic, 
                            int(st.session_state.pdf_year), 
                            int(st.session_state.pdf_month)
                        )

                    if final_rows:
                        st.subheader("3. 生成結果の確認")
                        df_res = pd.DataFrame(final_rows, columns=["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location"])
                        st.dataframe(df_res, use_container_width=True)
                        csv_buffer = io.StringIO()
                        df_res.to_csv(csv_buffer, index=False, encoding="utf_8_sig")
                        st.download_button(
                            label="📥 CSVをダウンロード",
                            data=csv_buffer.getvalue(),
                            file_name=f"schedule_{st.session_state.pdf_year}{st.session_state.pdf_month:02d}.csv",
                            mime="text/csv",
                            use_container_width=True
                        )
                except Exception as e:
                    st.error(f"エラー: {e}")
    else:
        st.session_state.pdf_year = None
        st.session_state.pdf_month = None

if __name__ == "__main__":
    main()
