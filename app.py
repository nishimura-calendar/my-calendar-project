import streamlit as st
import pandas as pd
import io
import practice_0 as p0

def main():
    st.set_page_config(page_title="シフト抽出ツール", layout="wide")
    
    if 'pdf_year' not in st.session_state: st.session_state.pdf_year = None
    if 'pdf_month' not in st.session_state: st.session_state.pdf_month = None
    if 'staff_name' not in st.session_state: st.session_state.staff_name = "田坂 友愛"

    st.title("🛡️ 関空免税店シフト抽出システム")
    
    with st.sidebar:
        st.header("設定")
        target_staff = st.text_input("抽出する名前", value=st.session_state.staff_name)
        st.session_state.staff_name = target_staff
        sheet_id = st.text_input("時程表シートID", value="1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE")
        
        st.divider()
        st.info("PDFをアップロードすると、年月が自動解析されます。")

    pdf_file = st.file_uploader("シフト表PDFをアップロード", type="pdf")

    if pdf_file:
        pdf_bytes = pdf_file.read()
        pdf_stream = io.BytesIO(pdf_bytes)

        # 1. 年月解析
        year, month = p0.extract_year_month_from_pdf(pdf_stream)
        if year and month:
            st.session_state.pdf_year = year
            st.session_state.pdf_month = month
            st.success(f"📅 解析対象: {year}年 {month}月")
        else:
            st.error("年月が判定できません。手動で設定するか、ファイルを確認してください。")
            col1, col2 = st.columns(2)
            st.session_state.pdf_year = col1.number_input("年", value=2026)
            st.session_state.pdf_month = col2.number_input("月", value=1, min_value=1, max_value=12)

        if st.button("CSVを作成する", type="primary", use_container_width=True):
            try:
                with st.spinner("PDFを解析中..."):
                    service = p0.get_gdrive_service(st.secrets)
                    
                    # 必須関数 ② PDF読み込み
                    pdf_dic = p0.pdf_reader(pdf_stream, target_staff)
                    if not pdf_dic:
                        st.error(f"「{target_staff}」さんが見つかりませんでした。名前の表記（スペースの有無など）を確認してください。")
                        return
                    
                    # 必須関数 ① 時程表取得
                    time_schedule_dic = p0.time_schedule_from_drive(service, sheet_id)
                    
                    # 必須関数 ③ データ統合
                    integrated_dic = p0.data_integration(pdf_dic, time_schedule_dic)
                    
                    # 4. 月間処理
                    final_rows = p0.process_full_month(
                        integrated_dic, 
                        st.session_state.pdf_year, 
                        st.session_state.pdf_month
                    )

                    if final_rows:
                        df_res = pd.DataFrame(final_rows, columns=[
                            "Subject", "Start Date", "Start Time", "End Date", "End Time", 
                            "All Day Event", "Description", "Location"
                        ])
                        
                        st.subheader("抽出結果プレビュー")
                        st.dataframe(df_res, use_container_width=True)

                        csv_buffer = io.StringIO()
                        df_res.to_csv(csv_buffer, index=False, encoding="utf_8_sig")
                        
                        st.download_button(
                            label="📥 Googleカレンダー用CSVを保存",
                            data=csv_buffer.getvalue(),
                            file_name=f"shift_{st.session_state.pdf_year}_{st.session_state.pdf_month}_{target_staff}.csv",
                            mime="text/csv",
                            use_container_width=True
                        )
                    else:
                        st.warning("該当するシフトデータが見つかりませんでした。")
            except Exception as e:
                st.error(f"実行エラー: {e}")

if __name__ == "__main__":
    main()
