import streamlit as st
import practice_0 as p0

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="PDF [0,0] Scanner", layout="wide")
st.title("🎯 PDF[0,0]特定・拠点照合システム")

drive, sheets = p0.get_unified_services()

if sheets:
    if 'time_dic' not in st.session_state:
        with st.spinner("マスター取得中..."):
            st.session_state.time_dic = p0.time_schedule_from_drive(sheets, SHEET_ID)
    
    uploaded_pdf = st.file_uploader("PDFをアップロード", type="pdf")

    if uploaded_pdf and st.button("解析実行", type="primary"):
        results, report_df = p0.scan_pdf_0_0_only(uploaded_pdf, st.session_state.time_dic)
        
        st.subheader("📋 判定レポート")
        st.table(report_df)

        if results:
            st.divider()
            for item in results:
                st.success(f"✅ 拠点「{item['key']}」の時程表を表示します")
                st.dataframe(item['time_schedule'], use_container_width=True)
        else:
            st.error("不一致のため表示できません。")
else:
    st.error("認証エラーが発生しました。Streamlit CloudのSecrets設定を確認してください。")
