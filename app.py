import streamlit as st
import practice_0 as p0
import pandas as pd
import base64
import re

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="PDF照合システム", layout="wide")
drive, sheets = p0.get_unified_services()

if 'time_dic' not in st.session_state and sheets:
    st.session_state.time_dic = p0.load_time_schedule(sheets, SHEET_ID)

uploaded_file = st.file_uploader("PDFアップロード", type="pdf")

if uploaded_file:
    # 第一関門: 年月入力
    manual_date = None
    match = re.search(r'(\d{4})[年\-_](\d{1,2})', uploaded_file.name)
    if not match:
        c1, c2 = st.columns(2)
        manual_date = (c1.number_input("年", 2026), c2.number_input("月", 1, 12))
        if not st.button("ファイル確認"): st.stop()

    res, msg = p0.analyze_pdf_structural(uploaded_file, st.session_state.time_dic.keys(), uploaded_file.name, manual_date)

    if res:
        # 第二関門: 拠点チェック (source: 9)
        loc_key = p0.normalize_text(res['location'])
        if loc_key not in st.session_state.time_dic:
            st.error(f"拠点「{res['location']}」は未登録です。")
            base64_pdf = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')
            st.markdown(f'<embed src="data:application/pdf;base64,{base64_pdf}" width="100%" height="500" type="application/pdf">', unsafe_allow_html=True)
            st.stop()

        # 第三関門: スタッフ選択・分離 (source: 9)
        target_staff = st.selectbox("スタッフを選択してください", ["該当なし"] + res['staff_list'])
        df = res['df']
        
        if target_staff != "該当なし":
            try:
                idx = df[df[0] == target_staff].index[0]
                # my_daily_shift: 本人行 + 下段 (source: 9)
                my_daily_shift = df.iloc[idx:idx+2, :]
                # other_daily_staff: 他人の氏名行のみ (source: 9)
                other_indices = [i for i in range(2, len(df), 2) if i != idx]
                other_daily_staff = df.iloc[other_indices, :]

                st.write("### 📅 My Daily Shift (本人+資格)")
                st.dataframe(my_daily_shift, use_container_width=True)
                st.write("### 👥 Other Daily Staff (他者氏名行のみ)")
                st.dataframe(other_daily_staff, use_container_width=True)
                st.write("### ⏰ Time Schedule")
                st.dataframe(st.session_state.time_dic[loc_key], use_container_width=True)
            except:
                st.error("target_staffが見つかりません。")
                st.stop()
    else:
        st.error(f"停止: {msg}")
        base64_pdf = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')
        st.markdown(f'<embed src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf">', unsafe_allow_html=True)
