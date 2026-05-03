import streamlit as st
import practice_0 as p0
import pandas as pd

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="勤務表解析", layout="wide")
st.title("🎯 PDF解析・配置ルール適用システム")

drive, sheets = p0.get_unified_services()
if sheets:
    if 'time_dic' not in st.session_state:
        with st.spinner("マスター取得中..."):
            st.session_state.time_dic = p0.time_schedule_from_drive(sheets, SHEET_ID)

    uploaded_pdf = st.file_uploader("PDFをアップロード", type="pdf")

    if uploaded_pdf and st.button("解析実行", type="primary"):
        res, report_df = p0.analyze_pdf_full(uploaded_pdf, st.session_state.time_dic.keys())
        
        if res:
            st.subheader("📋 解析レポート")
            st.table(report_df)
            
            # 配置確認用のプレビュー
            st.write("### 📅 日付・曜日・拠点 配置確認")
            header_df = pd.DataFrame([res['dates'], res['days']], index=["0: 日付", "1: 曜日"])
            st.dataframe(header_df)

            st.write(f"**1列目 拠点位置 [1,0]:** `{res['location']}`")

            st.write("### 👤 氏名・資格 構造（2行目以降）")
            for i, s in enumerate(res['staff']):
                st.info(f"行 {2+(i*2)}: **{s['name']}**  \n行 {2+(i*2)+1}: 資格：{s['license']}")

            # 時程表照合
            loc_key = p0.normalize_text(res['location'])
            if loc_key in st.session_state.time_dic:
                st.divider()
                st.success(f"拠点「{res['location']}」の時程表")
                st.dataframe(st.session_state.time_dic[loc_key], use_container_width=True)
        else:
            st.error("解析に失敗しました。")
