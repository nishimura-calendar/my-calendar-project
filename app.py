import streamlit as st
import practice_0 as p0
import pandas as pd
import base64

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"
st.set_page_config(page_title="PDF照合システム", layout="wide")

# 時程表マスターのロード
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
    res, msg = p0.analyze_pdf_structural(uploaded_file, st.session_state.time_dic.keys(), uploaded_file.name)

    # --- ① 不一致時の挙動 ---
    if not res:
        st.error(f"プログラム停止: {msg}")
        uploaded_file.seek(0)
        base64_pdf = base64.b64encode(uploaded_file.read()).decode('utf-8')
        st.markdown(f'<embed src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800" type="application/pdf">', unsafe_allow_html=True)
        st.stop()

    # --- ② サイドバー：ボタンをなくし、Enter確定にする ---
    with st.sidebar:
        st.title("👤 スタッフ選択")
        st.info("矢印キーで選択し、Enterで確定してください。")
        
        # st.selectboxは、矢印キーで選んでいる最中は値が確定せず、
        # Enterを押すかフォーカスを外すと確定するため、誤爆を防げます。
        target_staff = st.selectbox(
            "スタッフ一覧",
            options=["該当なし"] + res['staff_list'],
            index=0,
            key="target_staff_box"
        )

    # --- ③ 表示ロジック ---
    st.success(f"✅ {res['year']}年{res['month']}月 / 拠点: {res['location']}")
    
    if target_staff != "該当なし":
        df = res['df']
        loc_key = p0.normalize_text(res['location'])
        
        try:
            # 本人の2行
            idx = df[df[0] == target_staff].index[0]
            my_daily_shift = df.iloc[idx : idx+2, :]
            
            # 他スタッフ（拠点名行をスキップ）
            other_indices = []
            for i in range(2, len(df), 2):
                row_name = str(df.iloc[i, 0]).strip()
                if row_name != target_staff and p0.normalize_text(row_name) != loc_key:
                    other_indices.append(i)
            other_daily_staff = df.iloc[other_indices, :]

            # 拠点時程表
            time_schedule = st.session_state.time_dic.get(loc_key, None)

            # --- 描画 ---
            st.divider()
            st.subheader(f"📅 {target_staff} の個人シフト")
            st.dataframe(my_daily_shift, hide_index=True, use_container_width=True)

            st.subheader("👥 他スタッフの勤務状況")
            st.dataframe(other_daily_staff, hide_index=True, use_container_width=True)
            
            if time_schedule is not None:
                st.subheader(f"⏰ 拠点時程表: {res['location']}")
                st.dataframe(time_schedule, hide_index=True, use_container_width=True)

        except Exception as e:
            st.error(f"データ抽出エラー: {e}")
    else:
        st.info("サイドバーで名前を選択し、Enterキーを押してください。")
