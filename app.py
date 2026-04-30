import streamlit as st
import pandas as pd
import practice_0 as p0

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="PDF解析・確認", layout="wide")
st.title("📄 PDF解析プロセス確認")

drive_service, sheets_service = p0.get_unified_services()
if sheets_service:
    if 'time_dic' not in st.session_state:
        st.session_state.time_dic = p0.time_schedule_from_drive(sheets_service, SHEET_ID)
    time_dic = st.session_state.time_dic

    col1, col2 = st.columns(2)
    with col1:
        target_name = st.text_input("スタッフ名", value="自分")
    with col2:
        uploaded_file = st.file_uploader("PDFアップロード", type="pdf")

    if uploaded_file and target_name:
        # 解析実行
        raw_val, clean_val, result = p0.process_pdf_with_preview(uploaded_file, target_name, time_dic)
        
        # --- クレンジング前後の確認エリア ---
        st.subheader("🔍 ステップ1: [0,0]セルのクレンジング結果確認")
        c1, c2 = st.columns(2)
        with c1:
            st.info(f"**クレンジング前 (生データ):**\n\n`{raw_val}`")
        with c2:
            st.success(f"**クレンジング後 (new_location):**\n\n`{clean_val}`")
        # ----------------------------------

        if isinstance(result, str): # エラー（未登録拠点など）の場合
            st.error(result)
            st.stop()
        
        if result:
            st.success(f"照合成功：拠点「{result['key']}」")
            st.header("📊 抽出結果")
            res_df = pd.DataFrame([
                result['time_schedule'],
                result['my_daily_shift'],
                result['other_daily_shift']
            ], index=["時程", "自分", "他者"])
            st.dataframe(res_df, use_container_width=True)
