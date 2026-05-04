import streamlit as st
import practice_0 as p0
import pandas as pd
import base64
import re

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"
st.set_page_config(page_title="PDF照合システム", layout="wide")

if 'time_dic' not in st.session_state:
    st.session_state.time_dic = None

drive, sheets = p0.get_unified_services()
if sheets and st.session_state.time_dic is None:
    try:
        st.session_state.time_dic = p0.load_time_schedule(sheets, SHEET_ID)
    except Exception as e:
        st.error(f"マスターデータ読込失敗: {e}")

uploaded_file = st.file_uploader("PDFファイルをアップロード", type="pdf")

if uploaded_file:
    if st.session_state.time_dic is None:
        st.warning("マスターデータの準備を待っています...")
        st.stop()

    # 年月抽出
    match_y = re.search(r'(\d{4})', uploaded_file.name)
    match_m = re.search(r'(\d{1,2})', uploaded_file.name)
    manual_date = None
    if not (match_y and match_m):
        st.info("年月を特定できません。手動入力してください。")
        col1, col2 = st.columns(2)
        y_in = col1.number_input("年", 2020, 2030, 2026)
        m_in = col2.number_input("月", 1, 12, 1)
        if not st.button("ファイル内容を確認"): st.stop()
        manual_date = (y_in, m_in)

    res, msg = p0.analyze_pdf_structural(uploaded_file, st.session_state.time_dic.keys(), uploaded_file.name, manual_date)

    # --- ① 不一致時: 理由を表示しPDFを映す ---
    if not res:
        st.error(f"プログラム停止: {msg}")[cite: 3]
        base64_pdf = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')
        st.markdown(f'<embed src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf">', unsafe_allow_html=True)
        st.stop()

    # --- 正常時: UI表示 ---
    loc_key = p0.normalize_text(res['location'])
    st.success(f"✅ {res['year']}年{res['month']}月 / 拠点: {res['location']}")

    # --- ② 氏名選択: カーソル移動で確定させない設定 ---
    target_staff = st.selectbox(
        "スタッフを選択してください",
        options=["該当なし"] + res['staff_list'],
        index=None, # 初期値を空に
        placeholder="ここをクリックしてリストから選択...",
        key="staff_selector"
    )

    if target_staff:
        df = res['df']
        if target_staff != "該当なし":
            try:
                idx = df[df[0] == target_staff].index[0]
                my_daily_shift = df.iloc[idx : idx+2, :]
                other_indices = [i for i in range(2, len(df), 2) if df.iloc[i, 0] != target_staff]
                other_daily_staff = df.iloc[other_indices, :]

                st.divider()
                st.subheader(f"📅 {target_staff} のシフト")
                st.dataframe(my_daily_shift, hide_index=True, use_container_width=True)

                st.subheader("👥 他スタッフの状況")
                st.dataframe(other_daily_staff, hide_index=True, use_container_width=True)
                
                # --- ③ 時程表の表示復活 ---
                if loc_key in st.session_state.time_dic:
                    st.subheader(f"⏰ 時程表（マスター）: {res['location']}")
                    st.dataframe(st.session_state.time_dic[loc_key], hide_index=True, use_container_width=True)

            except Exception as e:
                st.error(f"表示エラー: {e}")
        else:
            st.info("全体データを表示します。")
            st.dataframe(df, hide_index=True, use_container_width=True)
