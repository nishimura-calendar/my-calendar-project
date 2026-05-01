import streamlit as st
import pandas as pd
import practice_0 as p0

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="シフト・時程管理システム", layout="wide")
st.title("📅 シフト・時程管理システム")

drive_service, sheets_service = p0.get_unified_services()

if sheets_service:
    if 'time_dic' not in st.session_state:
        with st.spinner("マスターデータ読込中..."):
            st.session_state.time_dic = p0.time_schedule_from_drive(sheets_service, SHEET_ID)
    
    time_dic = st.session_state.time_dic
    target_staff = st.sidebar.text_input("解析対象者名", value="西村 文宏")
    uploaded_pdf = st.sidebar.file_uploader("PDFをアップロード", type="pdf")

    if uploaded_pdf:
        # practice_0.py の関数を呼び出し
        y, m = p0.extract_year_month_from_text(uploaded_pdf.name)
        
        execute = False
        if not y or not m:
            st.warning("年月が自動判定できませんでした。")
            c1, c2 = st.columns(2)
            y = c1.number_input("年", value=2026)
            m = c2.number_input("月", value=1, min_value=1, max_value=12)
            if st.button("設定した年月で実行"): execute = True
        else:
            st.success(f"📅 {y}年{m}月 のファイルとして処理します。")
            if st.button("解析実行", type="primary"): execute = True

        if execute:
            result, err = p0.process_full_logic(uploaded_pdf, target_staff, time_dic, y, m)
            
            if err:
                st.error(err)
                if isinstance(result, pd.DataFrame): st.dataframe(result)
                st.stop()
            
            # 結果表示（3要素）
            st.divider()
            st.subheader(f"📄 自分のシフト ({target_staff}: 2行)")
            st.dataframe(pd.DataFrame(result['my_daily_shift']), use_container_width=True)

            st.subheader("👥 他者のシフト (各1行)")
            st.dataframe(pd.DataFrame(result['other_daily_shift']), use_container_width=True)

            st.subheader(f"🕒 時程表マスター (拠点: {result['key']})")
            st.dataframe(result['time_schedule_full'], use_container_width=True)
else:
    st.error("Google API認証失敗。Secretsを確認してください。")
