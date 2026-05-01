import streamlit as st
import practice_0 as p0

# スプレッドシートID
SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="PDF Key Scanner", layout="wide")
st.title("📄 PDF 0列目スキャン & 拠点照合システム")

drive, sheets = p0.get_unified_services()

if sheets:
    if 'time_dic' not in st.session_state:
        with st.spinner("マスターデータを取得中..."):
            st.session_state.time_dic = p0.time_schedule_from_drive(sheets, SHEET_ID)
    
    time_dic = st.session_state.time_dic

    with st.sidebar:
        st.success(f"マスター登録: {len(time_dic)} 拠点")
        if st.checkbox("Key一覧を表示"):
            st.write(list(time_dic.keys()))

    uploaded_pdf = st.file_uploader("勤務予定表（PDF）をアップロードしてください", type="pdf")

    if uploaded_pdf and st.button("全行スキャン実行", type="primary"):
        # ○×判定と時程表取得を実行
        results, debug_df = p0.scan_pdf_with_debug(uploaded_pdf, time_dic)
        
        # 1. 照合レポートを表示
        st.subheader("📋 0列目解析レポート（○×判定）")
        st.dataframe(debug_df, use_container_width=True)

        st.divider()

        # 2. ヒットした拠点の時程表を表示
        if results:
            st.success(f"✅ {len(results)} 件の拠点を特定しました。")
            for item in results:
                with st.container():
                    st.subheader(f"📍 拠点: {item['key']}")
                    st.dataframe(item['time_schedule'], use_container_width=True)
                    st.markdown("---")
        else:
            st.error("⚠️ 一致するKeyが見つかりませんでした。上のレポートの『クリーニング後』を確認してください。")
else:
    st.error("API認証エラー。secrets設定を確認してください。")
