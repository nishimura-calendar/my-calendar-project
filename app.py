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

uploaded_file = st.file_uploader("PDFファイルをアップロード", type="pdf")

if uploaded_file:
    # --- 年月抽出と入力ボックス表示の制御 (source: 9) ---
    match = re.search(r'(\d{4})[年\-_](\d{1,2})', uploaded_file.name)
    manual_date = None
    
    if not match:
        # ファイル名に年月がない場合のみ表示
        st.info("ファイル名から年月を特定できません。入力してください。")
        col1, col2 = st.columns(2)
        y_in = col1.number_input("年", 2020, 2030, 2026)
        m_in = col2.number_input("月", 1, 12, 1)
        if not st.button("ファイル確認"):
            st.stop()
        manual_date = (y_in, m_in)

    # 解析実行
    res, msg = p0.analyze_pdf_structural(uploaded_file, st.session_state.time_dic.keys(), uploaded_file.name, manual_date)

    if res:
        # 第二関門: 拠点チェック
        loc_key = p0.normalize_text(res['location'])
        if loc_key not in st.session_state.time_dic:
            st.error(f"拠点「{res['location']}」は時程表に登録されていません。")
            base64_pdf = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')
            st.markdown(f'<embed src="data:application/pdf;base64,{base64_pdf}" width="100%" height="500" type="application/pdf">', unsafe_allow_html=True)
            st.stop()

        # 第三関門: スタッフ選択 (source: 9)
        # keyを設定することで、選択状態を保持
        st.success(f"✅ 解析完了: {res['year']}年{res['month']}月 / 拠点: {res['location']}")
        
        target_staff = st.selectbox(
            "シフトカレンダーを作成するスタッフを選んで下さい。",
            ["該当なし"] + res['staff_list'],
            key="staff_selector" 
        )
        
        df = res['df']
        if target_staff != "該当なし":
            try:
                # 本人行(氏名)を探す
                idx = df[df[0] == target_staff].index[0]
                
                # my_daily_shift: 本人行 + 下段 (source: 9)
                my_daily_shift = df.iloc[idx : idx+2, :]
                
                # other_daily_staff: 他人の氏名行のみ (偶数行のみ抽出) (source: 9)
                other_indices = [i for i in range(2, len(df), 2) if df.iloc[i, 0] != target_staff]
                other_daily_staff = df.iloc[other_indices, :]

                st.divider()
                st.write(f"### 📅 {target_staff} のシフト (本人行+資格行)")
                st.dataframe(my_daily_shift, use_container_width=True, hide_index=True)
                
                st.write("### 👥 他スタッフの状況 (氏名行のみ)")
                st.dataframe(other_daily_staff, use_container_width=True, hide_index=True)
                
                st.write("### ⏰ 参照時程表")
                st.dataframe(st.session_state.time_dic[loc_key], use_container_width=True, hide_index=True)
                
            except Exception as e:
                st.error(f"target_staffが見つかりません。確認して下さい。({e})")
                base64_pdf = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')
                st.markdown(f'<embed src="data:application/pdf;base64,{base64_pdf}" width="100%" height="500" type="application/pdf">', unsafe_allow_html=True)
    else:
        # 第一関門不通過
        st.error(f"プログラム停止: {msg}")
        base64_pdf = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')
        st.markdown(f'<embed src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf">', unsafe_allow_html=True)
