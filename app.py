import streamlit as st
import practice_0 as p0

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="シフト・時程管理", layout="wide")
st.title("📅 シフト・時程 統合システム")

drive_service, sheets_service = p0.get_unified_services()

if sheets_service:
    time_dic = p0.time_schedule_from_drive(sheets_service, SHEET_ID)
    target_staff = st.sidebar.text_input("スタフ名", value="西村 文宏")
    uploaded_pdf = st.sidebar.file_uploader("PDFアップロード", type="pdf")

    if st.sidebar.button("解析実行"):
        if uploaded_pdf and target_staff:
            results, error_msg = p0.pdf_reader_final(uploaded_pdf, target_staff, time_dic)
            
            if error_msg:
                st.error(f"🛑 プログラム停止: {error_msg}")
                with st.expander("アップロードされたPDFの確認"):
                    st.write(f"ファイル名: {uploaded_pdf.name}")
                st.stop()
            
            for res in results:
                st.divider()
                st.header(f"📍 勤務地: {res['key']}")
                t1, t2, t3 = st.tabs(["自分のシフト", "他のスタッフ", "時程表 (時間表記変換済)"])
                with t1: st.dataframe(res['my_shift'], use_container_width=True)
                with t2: st.dataframe(res['other_shift'], use_container_width=True)
                with t3: st.dataframe(res['time_schedule'], use_container_width=True)
        else:
            st.warning("スタフ名とPDFを入力してください。")
