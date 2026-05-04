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
        st.error(f"マスター読込エラー: {e}")

uploaded_file = st.file_uploader("PDFファイルをアップロード", type="pdf")

if uploaded_file:
    # 年月抽出ロジック
    match_y = re.search(r'(\d{4})', uploaded_file.name)
    match_m = re.search(r'(\d{1,2})', uploaded_file.name)
    manual_date = None
    if not (match_y and match_m):
        st.info("年月を特定できません。手動入力してください。")
        col1, col2 = st.columns(2)
        y_in = col1.number_input("年", 2020, 2030, 2026)
        m_in = col2.number_input("月", 1, 12, 1)
        if not st.button("確認"): st.stop()
        manual_date = (y_in, m_in)

    res, msg = p0.analyze_pdf_structural(uploaded_file, st.session_state.time_dic.keys(), uploaded_file.name, manual_date)

    # --- ① 不一致時: 理由とPDFのみを表示 ---
    if not res:
        st.error(f"プログラム停止: {msg}")
        base64_pdf = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')
        pdf_display = f'<embed src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800" type="application/pdf">'
        st.markdown(pdf_display, unsafe_allow_html=True)
        st.stop()

    # --- 成功時 ---
    st.success(f"✅ {res['year']}年{res['month']}月 / 拠点: {res['location']}")

    # --- ② 氏名選択: st.formを使用して勝手な選択を防止 ---
    with st.form("staff_select_form"):
        target_staff = st.selectbox(
            "スタッフを選択（矢印キーで移動し、下の確定ボタンを押してください）",
            options=["該当なし"] + res['staff_list'],
            index=0, # 最初は「該当なし」
            help="名前を選んだあと、必ず下の『表示を確定する』ボタンを押してください。"
        )
        submit_button = st.form_submit_button("表示を確定する")

    # ボタンが押されたとき、または既に選択されている場合の表示処理
    if submit_button or target_staff:
        df = res['df']
        loc_key = p0.normalize_text(res['location'])

        if target_staff != "該当なし":
            try:
                # 本人データの抽出
                idx = df[df[0] == target_staff].index[0]
                my_daily_shift = df.iloc[idx : idx+2, :]
                
                # --- ③ other_daily_shift: 氏名=拠点名(key)の行を完全にスキップ ---
                other_indices = []
                for i in range(2, len(df), 2):
                    row_name = str(df.iloc[i, 0]).strip()
                    # 本人を除外 AND 拠点名(res['location'])を除外
                    if row_name != target_staff and p0.normalize_text(row_name) != loc_key:
                        other_indices.append(i)
                
                other_daily_staff = df.iloc[other_indices, :]

                st.divider()
                st.subheader(f"📅 {target_staff} の個人シフト")
                st.dataframe(my_daily_shift, hide_index=True, use_container_width=True)

                st.subheader("👥 他スタッフの勤務状況（拠点名行を除く）")
                st.dataframe(other_daily_staff, hide_index=True, use_container_width=True)
                
                if loc_key in st.session_state.time_dic:
                    st.subheader(f"⏰ 時程表: {res['location']}")
                    st.dataframe(st.session_state.time_dic[loc_key], hide_index=True, use_container_width=True)

            except Exception as e:
                st.error(f"表示エラー: {e}")
        else:
            st.info("全体データを表示します。")
            st.dataframe(df, hide_index=True, use_container_width=True)
