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
        st.error(f"マスター読込失敗: {e}")

uploaded_file = st.file_uploader("PDFファイルをアップロード", type="pdf")

if uploaded_file:
    # PDF解析
    res, msg = p0.analyze_pdf_structural(uploaded_file, st.session_state.time_dic.keys(), uploaded_file.name)

    # ① 不一致時：理由＋PDF表示
    if not res:
        st.error(f"プログラム停止: {msg}")
        uploaded_file.seek(0)
        base64_pdf = base64.b64encode(uploaded_file.read()).decode('utf-8')
        pdf_display = f'<embed src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800" type="application/pdf">'
        st.markdown(pdf_display, unsafe_allow_html=True)
        st.stop()

    # --- 第一関門通過後 ---
    # 代替案：サイドバーに選択リストを表示。これで矢印キー（↑↓）でサクサク選べます。
    with st.sidebar:
        st.title("👤 スタッフ選択")
        target_staff = st.radio(
            "一覧から選んでください（矢印キーで移動可能）",
            options=["該当なし"] + res['staff_list'],
            index=0
        )

    # メイン画面表示
    st.success(f"✅ {res['year']}年{res['month']}月 / 拠点: {res['location']}")
    
    df = res['df']
    loc_key = p0.normalize_text(res['location'])

    if target_staff != "該当なし":
        try:
            # 本人データ
            idx = df[df[0] == target_staff].index[0]
            my_daily_shift = df.iloc[idx : idx+2, :]
            
            # ③ 他スタッフ（拠点名行をスキップ）
            other_indices = []
            for i in range(2, len(df), 2):
                row_name = str(df.iloc[i, 0]).strip()
                if row_name != target_staff and p0.normalize_text(row_name) != loc_key:
                    other_indices.append(i)
            
            other_daily_staff = df.iloc[other_indices, :]

            # 表示
            st.divider()
            st.subheader(f"📅 {target_staff} の個人シフト")
            st.dataframe(my_daily_shift, hide_index=True, use_container_width=True)

            st.subheader("👥 他スタッフの勤務状況")
            st.dataframe(other_daily_staff, hide_index=True, use_container_width=True)
            
            if loc_key in st.session_state.time_dic:
                st.subheader(f"⏰ 拠点時程表: {res['location']}")
                st.dataframe(st.session_state.time_dic[loc_key], hide_index=True, use_container_width=True)

        except Exception as e:
            st.error(f"表示エラー: {e}")
    else:
        # 該当なし（初期状態）は全体表示と、一応PDFも出しておく
        st.info("スタッフを左側のリストから選択してください。")
        st.dataframe(df, hide_index=True, use_container_width=True)
        
        # PDF表示
        with st.expander("元のPDFを表示"):
            uploaded_file.seek(0)
            base64_pdf = base64.b64encode(uploaded_file.read()).decode('utf-8')
            st.markdown(f'<embed src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf">', unsafe_allow_html=True)
