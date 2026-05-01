import streamlit as st
import practice_0 as p0

# スプレッドシートID
SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="PDF Schedule Matcher", layout="wide")
st.title("📄 PDF拠点照合 & 時程表表示")

drive_service, sheets_service = p0.get_unified_services()

if sheets_service:
    if 'time_dic' not in st.session_state:
        with st.spinner("マスターデータを取得中..."):
            st.session_state.time_dic = p0.time_schedule_from_drive(sheets_service, SHEET_ID)
    
    time_dic = st.session_state.time_dic

    with st.sidebar:
        st.success(f"マスター登録数: {len(time_dic)} 拠点")
        with st.expander("Key一覧"):
            st.write(list(time_dic.keys()))

    uploaded_pdf = st.file_uploader("PDFを選択してください", type="pdf")

    if uploaded_pdf and st.button("解析実行", type="primary"):
        result = p0.get_key_and_schedule(uploaded_pdf, time_dic)
        
        if result:
            st.success(f"📍 拠点特定: {result['key']}")
            st.caption(f"PDF 0列目抽出値: {result['raw']}")
            
            st.subheader("🕒 時程表データ")
            st.dataframe(result['time_schedule'], use_container_width=True)
        else:
            st.error("⚠️ PDFの0列目から一致するKeyが見つかりませんでした。")
else:
    st.error("API認証エラー。secretsの設定を確認してください。")
