import streamlit as st
import practice_0 as p0
import base64
import re
from datetime import datetime

st.set_page_config(layout="wide")

# 1. 時程表読込 (時程表_7.xlsx を参照)
if 'time_dic' not in st.session_state:
    try:
        st.session_state.time_dic = p0.process_master_file("時程表_7.xlsx")
    except:
        st.error("時程表_7.xlsx が見つかりません。")

# 2. pdfアップロード
uploaded_file = st.file_uploader("PDFファイルをアップロード", type="pdf")

if uploaded_file:
    # ファイル名から年月抽出
    fname = uploaded_file.name
    match_y = re.search(r'(\d{4})', fname)
    match_m = re.search(r'(\d{1,2})', fname)
    
    if match_y and match_m:
        y, m = int(match_y.group(1)), int(match_m.group(1))
        is_ready = True
    else:
        # 不明箇所の入力を促す
        st.warning("ファイル名から年月を取得できません。")
        y = st.number_input("年", value=2024)
        m = st.number_input("月", min_value=1, max_value=12)
        is_ready = st.button("ファイル確認")

    if is_ready:
        # 第一関門
        with open("temp.pdf", "wb") as f: f.write(uploaded_file.getbuffer())
        res, msg = p0.analyze_pdf("temp.pdf", y, m)
        
        if res is None:
            st.error(f"第一関門失敗: {msg}")
            # PDF表示して停止
            with open("temp.pdf", "rb") as f:
                base64_pdf = base64.b64encode(f.read()).decode('utf-8')
            st.markdown(f'<embed src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800">', unsafe_allow_html=True)
            st.stop()
            
        # 第二関門
        loc = res['location']
        if loc not in st.session_state.time_dic:
            st.error(f"{loc} は時程表の勤務地には設定されていません。確認が必要です。")
            with open("temp.pdf", "rb") as f:
                base64_pdf = base64.b64encode(f.read()).decode('utf-8')
            st.markdown(f'<embed src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800">', unsafe_allow_html=True)
            st.stop()
            
        # 第三関門
        st.write("### シフトカレンダーを作成するスタッフを選んで下さい。")
        target_staff = st.selectbox("スタッフ一覧", ["該当なし"] + res['staff_list'])
        
        if target_staff != "該当なし":
            df = res['df']
            # target_staff検索
            try:
                idx = df[df[0] == target_staff].index[0]
                my_daily_shift = df.iloc[idx : idx+2, :]
                other_daily_shift = df.drop([idx, idx+1]).iloc[2:, :]
                
                # 表示
                st.subheader(f"【{target_staff}】の表示")
                st.write("個人シフト(my_daily_shift)")
                st.dataframe(my_daily_shift)
                st.write("他スタッフ(other_daily_shift)")
                st.dataframe(other_daily_shift)
                st.write("時程表(time_schedule)")
                st.dataframe(st.session_state.time_dic[loc])
            except:
                st.error("target_staffが見つかりません。確認して下さい。")
                st.stop()
