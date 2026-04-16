import streamlit as st
import pandas as pd
import io
import practice_0 as p0
import pdfplumber
import datetime
import calendar

def main():
    st.set_page_config(page_title="カレンダー作成ツール", layout="centered")
    
    if 'pdf_year' not in st.session_state: st.session_state.pdf_year = None
    if 'pdf_month' not in st.session_state: st.session_state.pdf_month = None
    if 'staff_name' not in st.session_state: st.session_state.staff_name = "西村 文宏"

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
        
        # ファイル名からの抽出を「絶対的な正」とする
        fname_y, fname_m = p0.extract_year_month_from_text(pdf_file.name)
        # PDF内部テキストからの抽出
        pdf_y, pdf_m = p0.extract_year_month_from_pdf(pdf_stream)
        
        # 最終的な適用年月を決定（ファイル名優先）
        apply_y = fname_y if fname_y else pdf_y
        apply_m = fname_m if fname_m else pdf_m
        
        st.session_state.pdf_year = apply_y
        st.session_state.pdf_month = apply_m
        
        mismatch_reason = []
        if apply_y and apply_m:
            # 不一致のチェック（警告用）
            # 1. ファイル名とPDF内部の矛盾
            if fname_y and pdf_y and (fname_y != pdf_y or fname_m != pdf_m):
                mismatch_reason.append(f"ファイル名({fname_y}/{fname_m})とPDF内部({pdf_y}/{pdf_m})が異なります。ファイル名を優先します。")

            # 2. 月末日数のチェック
            expected_days = calendar.monthrange(apply_y, apply_m)[1]
            actual_max_day = p0.extract_max_day_from_pdf(pdf_stream)
            if actual_max_day and actual_max_day != expected_days:
                mismatch_reason.append(f"指定月の日数({expected_days}日)とPDF内の最終日({actual_max_day}日)が一致しません。")

            # 3. 曜日のチェック
            first_day = datetime.date(apply_y, apply_m, 1)
            weekdays = ["月", "火", "水", "木", "金", "土", "日"]
            expected_wd = weekdays[first_day.weekday()]
            actual_wd = p0.extract_first_weekday_from_pdf(pdf_stream)
            if actual_wd and actual_wd != expected_wd:
                mismatch_reason.append(f"カレンダーの1日({expected_wd}曜)とPDF記載の曜日({actual_wd}曜)が異なります。")

        # --- 表示制御 ---
        if mismatch_reason:
            st.warning("⚠️ 整合性チェックにより以下の懸念が見つかりました：")
            for reason in mismatch_reason:
                st.write(f"- {reason}")
            
            st.info(f"適用される解析設定: {apply_y}年{apply_m}月")
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
            # 不備がない場合は年月を表示せず、受理メッセージのみ
            st.success(f"📁 {pdf_file.name} を正常に受理しました。")

        # 実行ボタン
        if apply_y and apply_m:
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
                            int(apply_y), 
                            int(apply_m)
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
                            file_name=f"schedule_{apply_y}{apply_m:02d}_{target_staff}.csv",
                            mime="text/csv",
                            use_container_width=True
                        )
                except Exception as e:
                    st.error(f"解析中にエラーが発生しました: {e}")
        else:
            st.error("ファイル名から年月を特定できません。")
    else:
        st.session_state.pdf_year = None
        st.session_state.pdf_month = None

if __name__ == "__main__":
    main()
