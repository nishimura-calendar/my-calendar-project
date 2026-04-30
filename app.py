import streamlit as st
import pandas as pd
import practice_0 as p0

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="PDFシフト解析", layout="wide")
st.title("📄 PDFシフト解析と時程照合")

drive_service, sheets_service = p0.get_unified_services()
if sheets_service:
    if 'time_dic' not in st.session_state:
        st.session_state.time_dic = p0.time_schedule_from_drive(sheets_service, SHEET_ID)
    time_dic = st.session_state.time_dic

    col_in1, col_in2 = st.columns(2)
    with col_in1:
        target_name = st.text_input("スタッフ名（例：四村和義）", value="四村 和義")
    with col_in2:
        uploaded_file = st.file_uploader("PDFアップロード", type="pdf")

    if uploaded_file and target_name:
        raw_val, clean_val, result = p0.process_pdf_with_cleaning(uploaded_file, target_name, time_dic)
        
        st.subheader("🔍 ステップ1: [0,0]セルの解析確認")
        c1, c2 = st.columns(2)
        with c1:
            st.info(f"**クレンジング前 (生データ):**\n\n`{raw_val}`")
        with c2:
            st.success(f"**クレンジング後 (new_location):**\n\n`{clean_val}`")

        if isinstance(result, str):
            st.error(result)
            st.stop()
        
        if result:
            st.success(f"照合成功：拠点「{result['key']}」")
            st.header("📊 抽出結果")
            final_df = pd.DataFrame([
                result['time_schedule'],
                result['my_daily_shift'],
                result['other_daily_shift']
            ], index=["時程表", "自分", "他者"])
            st.dataframe(final_df, use_container_width=True)
