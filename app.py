import streamlit as st
import practice_0 as p0
import pandas as pd
import base64
import re  

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="PDF厳密構造化", layout="wide")
st.title("🎯 PDF厳密構造化・照合システム")

# 認証とサービス取得
drive, sheets = p0.get_unified_services()
if not sheets:
    st.error("認証エラー：Secrets設定を確認してください。")
    st.stop()

# 時程表（マスター）の読み込み
if 'time_dic' not in st.session_state:
    with st.spinner("マスターデータを取得中..."):
        st.session_state.time_dic = p0.load_time_schedule(sheets, SHEET_ID)

# PDFアップロード
uploaded_file = st.file_uploader("PDFファイルをアップロード (例: 免税店シフト表...ル 2026.pdf)", type="pdf")

if uploaded_file:
    # 1. ファイル名から年月を抽出
    manual_date = None
    # 提供されたファイル名「...ル 2026.pdf」等に対応
    match = re.search(r'(\d{4})', uploaded_file.name)
    
    if not match:
        st.warning("ファイル名から年を特定できません。手動入力してください。")
        col1, col2 = st.columns(2)
        y = col1.number_input("年", value=2026, step=1)
        m = col2.number_input("月", min_value=1, max_value=12, value=1)
        manual_date = (y, m)
        if not st.button("ファイル内容を確認する"):
            st.stop()
    else:
        # ファイル名に年しかない場合は月を補完（今回のPDFは2026年1月度）
        year_found = int(match.group(1))
        month_match = re.search(r'(\d{1,2})月', uploaded_file.name)
        month_found = int(month_match.group(1)) if month_match else 1
        manual_date = (year_found, month_found)

    # 2. 解析実行
    with st.spinner("PDF構造解析中..."):
        res, msg = p0.analyze_pdf_structural(uploaded_file, st.session_state.time_dic.keys(), uploaded_file.name, manual_date)

    if res:
        # 第2関門: 拠点照合
        loc_key = p0.normalize_text(res['location'])
        if loc_key not in st.session_state.time_dic:
            st.error(f"「{res['location']}」は時程表に未登録です。")
            base64_pdf = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')
            st.markdown(f'<embed src="data:application/pdf;base64,{base64_pdf}" width="100%" height="500" type="application/pdf">', unsafe_allow_html=True)
            st.stop()

        # 第3関門: スタッフ選択
        st.success(f"✅ 第一・第二関門通過 (拠点: {res['location']})")
        target_staff = st.selectbox("シフトカレンダーを作成するスタッフを選んで下さい。", ["該当なし"] + res['staff_list'])
        
        if target_staff != "該当なし":
            df = res['df']
            # スタッフ行の分離ロジック
            try:
                idx = df[df[0] == target_staff].index[0]
                st.write(f"### 📅 {target_staff} のシフト")
                st.dataframe(df.iloc[idx:idx+2, :], use_container_width=True)
                
                st.write("### 👥 他のスタッフのシフト")
                st.dataframe(df.drop([idx, idx+1]).iloc[2:, :], use_container_width=True)
            except Exception as e:
                st.error(f"スタッフ抽出エラー: {e}")
            
            st.write("### ⏰ 参照時程表")
            st.dataframe(st.session_state.time_dic[loc_key], use_container_width=True)
    else:
        st.error(f"❌ プログラム停止: {msg}")
        # PDFを表示
        base64_pdf = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')
        st.markdown(f'<embed src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf">', unsafe_allow_html=True)
