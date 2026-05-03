import streamlit as st
import practice_0 as p0
import pandas as pd

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="PDF厳密構造化", layout="wide")
st.title("🎯 PDF厳密構造化・照合システム")

# 1. 認証と時程表読み込み (引数の受け取りを修正)
drive, sheets = p0.get_unified_services()

if sheets:
    if 'time_dic' not in st.session_state:
        with st.spinner("マスター時程表を読み込み中..."):
            # ここでAttributeErrorが発生しないよう修正
            st.session_state.time_dic = p0.time_schedule_from_drive(sheets, SHEET_ID)
    
    uploaded_pdf = st.file_uploader("PDFファイルをアップロード", type="pdf")

    if uploaded_pdf and st.button("解析・構造化実行", type="primary"):
        res, report_df = p0.analyze_pdf_full(uploaded_pdf, st.session_state.time_dic.keys())
        
        if res:
            st.subheader("📋 解析レポート")
            st.table(report_df)
            
            st.write("### 🗂 構造化プレビュー (0:日付 / 1:曜日 / 2:氏名 / 3:資格)")
            st.dataframe(res['df'], use_container_width=True)

            # 時程表照合
            loc_key = p0.normalize_text(res['location'])
            if loc_key in st.session_state.time_dic:
                st.divider()
                st.success(f"✅ 拠点「{res['location']}」の時程表")
                st.dataframe(st.session_state.time_dic[loc_key], use_container_width=True)
        else:
            st.error("PDFの解析に失敗しました。")
else:
    st.error("認証エラー：Secrets設定またはGoogleサービス接続を確認してください。")
