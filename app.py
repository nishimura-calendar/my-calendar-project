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
        y, m = p0.extract_year_month_from_text(uploaded_pdf.name)
        
        execute = False
        if not y or not m:
            st.warning("年月を手動設定してください。")
            c1, c2 = st.columns(2)
            y = c1.number_input("年", value=2026)
            m = c2.number_input("月", value=1, min_value=1, max_value=12)
            if st.button("実行"): execute = True
        else:
            st.success(f"📅 {y}年{m}月 として処理します。")
            if st.button("解析実行", type="primary"): execute = True

        if execute:
            result, err = p0.process_full_logic(uploaded_pdf, target_staff, time_dic, y, m)
            
            if err:
                st.error(err)
                if isinstance(result, pd.DataFrame): 
                    st.info("解析途中のテーブル構造:")
                    st.dataframe(result)
                st.stop()
            
            st.divider()
            
            # --- ここから表示の訂正 ---
            st.subheader(f"📄 抽出されたシフト: {target_staff} さん")
            
            # 本人のシフト（2行分）をデータフレーム化
            # カラム名を日付（1, 2, 3...）に設定するとさらに見やすくなります
            df_my = pd.DataFrame(result['my_daily_shift'])
            st.dataframe(df_my, use_container_width=True, hide_index=True)

            with st.expander("👥 他者のシフト（参考）"):
                df_others = pd.DataFrame(result['other_daily_shift'])
                st.dataframe(df_others, use_container_width=True, hide_index=True)

            st.subheader(f"🕒 対応する時程表: {result['key']}")
            st.dataframe(result['time_schedule_full'], use_container_width=True, hide_index=True)
else:
    st.error("Google API認証に失敗しました。")
