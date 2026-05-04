import streamlit as st
import practice_0 as p0
import pandas as pd
import base64

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="PDF厳密構造化", layout="wide")
st.title("🎯 PDF厳密構造化・照合システム")

drive, sheets = p0.get_unified_services()
if not sheets:
    st.error("認証エラー")
    st.stop()

# 時程表読込
if 'time_dic' not in st.session_state:
    st.session_state.time_dic = p0.load_time_schedule(sheets, SHEET_ID)

# 1. PDFアップロード
uploaded_file = st.file_uploader("PDFファイルをアップロード", type="pdf")

if uploaded_file:
    # 第一関門：年月抽出・入力 (source: 9)
    manual_date = None
    match = re.search(r'(\d{4})[年\-_](\d{1,2})', uploaded_file.name)
    if not match:
        col1, col2 = st.columns(2)
        y = col1.number_input("年", value=2026)
        m = col2.number_input("月", min_value=1, max_value=12)
        manual_date = (y, m)
        if not st.button("ファイル確認"): st.stop()

    # 解析実行
    res, msg = p0.analyze_pdf_structural(uploaded_file, st.session_state.time_dic.keys(), uploaded_file.name, manual_date)

    if res:
        # 第2関門: locationチェック (source: 9)
        loc_key = p0.normalize_text(res['location'])
        if loc_key not in st.session_state.time_dic:
            st.error(f"「{res['location']}」は時程表に未登録です。確認が必要です。")
            # PDFを表示して停止
            base64_pdf = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')
            st.markdown(f'<embed src="data:application/pdf;base64,{base64_pdf}" width="700" height="500" type="application/pdf">', unsafe_allow_html=True)
            st.stop()

        # 第3関門: スタッフ選択 (source: 9)
        st.success(f"第1・第2関門 通過 (location: {res['location']})")
        target_staff = st.selectbox("シフトカレンダーを作成するスタッフを選んで下さい。", ["該当なし"] + res['staff_list'])
        
        if target_staff != "該当なし":
            # データの振り分け
            df = res['df']
            # target_staff行を探す (2行目以降)
            idx = df[df[0] == target_staff].index[0]
            my_shift = df.iloc[idx:idx+2, :] # 氏名＋資格(下段)
            other_shift = df.drop([idx, idx+1]).iloc[2:, :] # それ以外
            
            st.divider()
            st.write("### 📅 My Daily Shift")
            st.dataframe(my_shift)
            
            st.write("### 👥 Other Daily Shift")
            st.dataframe(other_shift)
            
            st.write("### ⏰ Time Schedule (15分刻み変換済)")
            st.dataframe(st.session_state.time_dic[loc_key])
    else:
        st.error(f"プログラム停止: {msg}")
        # PDF表示
        base64_pdf = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')
        st.markdown(f'<embed src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600px" type="application/pdf">', unsafe_allow_html=True)
