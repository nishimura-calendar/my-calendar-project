import streamlit as st
import practice_0 as p0
import pandas as pd

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="勤務表構造化システム", layout="wide")
st.title("🎯 PDF厳密構造化・照合")

drive, sheets = p0.get_unified_services()
if sheets:
    if 'time_dic' not in st.session_state:
        with st.spinner("マスター取得中..."):
            st.session_state.time_dic = p0.time_schedule_from_drive(sheets, SHEET_ID)

    uploaded_pdf = st.file_uploader("PDFをアップロード", type="pdf")

    if uploaded_pdf and st.button("解析・構造化実行", type="primary"):
        res, report_df = p0.analyze_pdf_full(uploaded_pdf, st.session_state.time_dic.keys())
        
        if res:
            st.subheader("📋 座標レポート")
            st.table(report_df)
            
            st.write("### 🗂 構造化データ (0:日付 / 1:曜日 / 2:氏名 / 3:資格)")
            st.dataframe(res['df'], use_container_width=True)

            # CSVダウンロードボタン (確認用)
            csv = res['df'].to_csv(index=False).encode('utf-8-sig')
            st.download_button("構造化CSVをダウンロード", csv, "structured_shift.csv", "text/csv")

            # 時程表照合
            loc_key = p0.normalize_text(res['location'])
            if loc_key in st.session_state.time_dic:
                st.divider()
                st.success(f"✅ 拠点「{res['location']}」の時程表を表示")
                st.dataframe(st.session_state.time_dic[loc_key], use_container_width=True)
        else:
            st.error("解析に失敗しました。")
