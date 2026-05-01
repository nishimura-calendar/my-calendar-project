import streamlit as st
import practice_0 as p0

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="PDF Key Scanner", layout="wide")
st.title("🔍 PDF全行スキャン & 拠点照合表示")

drive, sheets = p0.get_unified_services()

if sheets:
    if 'time_dic' not in st.session_state:
        # 時程表から勤務地(A列)をKeyにして辞書登録[cite: 1]
        st.session_state.time_dic = p0.time_schedule_from_drive(sheets, SHEET_ID)
    
    time_dic = st.session_state.time_dic
    uploaded_pdf = st.file_uploader("PDFファイルをアップロード", type="pdf")

    if uploaded_pdf and st.button("全行スキャン実行"):
        # PDFの0列目を全てのKeyを対象に検索[cite: 1]
        results = p0.scan_pdf_for_all_keys(uploaded_pdf, time_dic)
        
        if results:
            st.success(f"{len(results)} 件の拠点がヒットしました")
            for item in results:
                # ヒットしたKeyとtime_scheduleを表示[cite: 1]
                with st.expander(f"📍 ヒットしたKey: {item['key']} (PDF {item['pdf_row']}行目)"):
                    st.write(f"**PDF抽出テキスト:** {item['pdf_text']}")
                    st.dataframe(item['time_schedule'], use_container_width=True)
        else:
            st.warning("一致するKeyは見つかりませんでした。抽出されたテキストを確認してください。")
