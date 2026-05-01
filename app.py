import streamlit as st
import practice_0 as p0

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="時程照合システム", layout="wide")
st.title("🕒 拠点Key・時程表 照合")

drive_service, sheets_service = p0.get_unified_services()

if sheets_service:
    # マスター一括読込
    if 'time_dic' not in st.session_state:
        with st.spinner("マスター読込中..."):
            st.session_state.time_dic = p0.time_schedule_from_drive(sheets_service, SHEET_ID)
    
    time_dic = st.session_state.time_dic

    # サイドバー設定
    st.sidebar.header("設定")
    st.sidebar.info(f"読み込み済みKey数: {len(time_dic)}")
    with st.sidebar.expander("マスターのKey一覧"):
        st.write(list(time_dic.keys()))

    uploaded_pdf = st.file_uploader("勤務表PDFをアップロード", type="pdf")

    if uploaded_pdf:
        if st.button("Keyと時程を表示", type="primary"):
            result = p0.get_key_and_schedule(uploaded_pdf, time_dic)
            
            if result:
                st.success(f"✅ 拠点特定成功: {result['key']}")
                
                col1, col2 = st.columns([1, 3])
                with col1:
                    st.metric("判定されたKey", result['key'])
                    st.caption(f"PDF[0,0]取得値: {result['raw_pdf_val']}")
                
                with col2:
                    st.subheader("🕒 該当拠点の時程表 (time_schedule)")
                    st.dataframe(result['time_schedule'], use_container_width=True)
            else:
                st.error("⚠️ 拠点を特定できませんでした。")
                st.info("PDFの[0,0]に含まれる文字列が、マスターのKey一覧にあるか確認してください。")
else:
    st.error("Google API認証失敗。secretsを確認してください。")
