import streamlit as st
import practice_0 as p0

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="Key & TimeSchedule Viewer", layout="wide")
st.title("📄 PDF拠点照合 & 時程表表示")

drive, sheets = p0.get_unified_services()

if sheets:
    if 'time_dic' not in st.session_state:
        st.session_state.time_dic = p0.time_schedule_from_drive(sheets, SHEET_ID)
    
    time_dic = st.session_state.time_dic
    
    with st.sidebar:
        st.info(f"マスター読込数: {len(time_dic)}")
        st.expander("登録済みKey一覧").write(list(time_dic.keys()))

    uploaded_pdf = st.file_uploader("勤務表PDFをアップロード", type="pdf")

    if uploaded_pdf and st.button("解析実行", type="primary"):
        result = p0.get_key_and_schedule(uploaded_pdf, time_dic)
        
        if result:
            st.success(f"📍 拠点特定: {result['key']}")
            st.caption(f"PDF[0,0]生データ: {result['raw']}")
            
            # 結果の表示（A-C列 + 時刻変換済み時間列）
            st.subheader("🕒 抽出された時程表 (time_schedule)")
            st.dataframe(result['time_schedule'], use_container_width=True)
        else:
            st.error("拠点Keyが一致しません。マスターのA列設定を確認してください。")
