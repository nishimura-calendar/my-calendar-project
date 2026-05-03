import streamlit as st
import practice_0 as p0
import pandas as pd

# スプレッドシートID
SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="PDF解析システム", layout="wide")
st.title("🎯 PDF[0,0]特定・拠点照合システム")

# 1. 時程表を読み込む
drive, sheets = p0.get_unified_services()
if sheets:
    if 'time_dic' not in st.session_state:
        with st.spinner("1. マスター時程表を取得中..."):
            st.session_state.time_dic = p0.time_schedule_from_drive(sheets, SHEET_ID)
            st.success("時程表の読み込みが完了しました")

    # 2. PDFファイルのアップロード[cite: 8, 10]
    uploaded_pdf = st.file_uploader("2. PDFファイルをアップロード", type="pdf")

    # 3. PDF解析の実行
    if uploaded_pdf and st.button("3. 解析実行", type="primary"):
        res, report_df = p0.analyze_pdf_full(uploaded_pdf, st.session_state.time_dic)
        
        if res:
            st.subheader("📋 解析・判定レポート")
            st.table(report_df)
            
            # 拠点に基づいた時程表の表示
            loc_key = p0.normalize_text(res['location'])
            if loc_key in st.session_state.time_dic:
                st.divider()
                st.success(f"✅ 拠点「{res['location']}」の時程表を表示します")
                st.dataframe(st.session_state.time_dic[loc_key], use_container_width=True)
            else:
                st.error(f"拠点 '{res['location']}' に対応する時程表が見つかりません。")
            
            # デバッグ用：PDF内部構造のプレビュー
            with st.expander("PDF解析データプレビュー"):
                st.dataframe(res['df'])
        else:
            st.error("PDFの解析に失敗しました。ファイル形式を確認してください。")
else:
    st.error("認証エラーが発生しました。Secrets設定を確認してください。")
