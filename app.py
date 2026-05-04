import streamlit as st
import practice_0 as p0
import pandas as pd
import base64
import re

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="PDF照合システム", layout="wide")

# 1. サービスの取得と初期化 (AttributeError対策)
if 'time_dic' not in st.session_state:
    st.session_state.time_dic = None  # 初期値

drive, sheets = p0.get_unified_services()

if st.session_state.time_dic is None and sheets:
    try:
        # マスターデータを先に読み込む
        st.session_state.time_dic = p0.load_time_schedule(sheets, SHEET_ID)
    except Exception as e:
        st.error(f"マスターデータの読み込みに失敗しました。再読み込みしてください。: {e}")

uploaded_file = st.file_uploader("PDFファイルをアップロード", type="pdf")

if uploaded_file:
    # 2. マスターデータ読み込み完了を待機
    if st.session_state.time_dic is None:
        st.warning("時程表の準備中です。少々お待ちください...")
        st.stop()

    # 3. 年月抽出の判定 (ご提案のロジック)
    # 4桁＝年、最初に見つかる1-2桁＝月
    match_y = re.search(r'(\d{4})', uploaded_file.name)
    match_m = re.search(r'(\d{1,2})', uploaded_file.name)
    
    manual_date = None
    if not (match_y and match_m):
        # 判定できない時だけ入力欄を表示
        st.info("ファイル名から年月を特定できません。入力してください。")
        col1, col2 = st.columns(2)
        y_in = col1.number_input("年", 2020, 2030, 2026)
        m_in = col2.number_input("月", 1, 12, 1)
        if not st.button("ファイル内容を確認"):
            st.stop()
        manual_date = (y_in, m_in)

    # 4. 解析実行 (自動で次へ)
    res, msg = p0.analyze_pdf_structural(
        uploaded_file, 
        st.session_state.time_dic.keys(), 
        uploaded_file.name, 
        manual_date
    )

    if res:
        # 第二関門: 拠点チェック
        loc_key = p0.normalize_text(res['location'])
        if loc_key not in st.session_state.time_dic:
            st.error(f"拠点「{res['location']}」は未登録です。")
            st.stop()

        st.success(f"✅ {res['year']}年{res['month']}月 / 拠点: {res['location']}")
        
        # 5. スタッフ選択 (誤クリック防止の空初期値)
        target_staff = st.selectbox(
            "スタッフを選んで下さい。",
            options=["該当なし"] + res['staff_list'],
            index=None,
            placeholder="ここをクリックして氏名を選択...",
            key="staff_selector"
        )
        
        if target_staff:
            df = res['df']
            if target_staff != "該当なし":
                try:
                    idx = df[df[0] == target_staff].index[0]
                    # my_daily_shift: 本人行 + その下段 (source: 9)
                    my_daily_shift = df.iloc[idx : idx+2, :]
                    # other_daily_staff: 他人の氏名行のみ (source: 9)
                    other_indices = [i for i in range(2, len(df), 2) if df.iloc[i, 0] != target_staff]
                    other_daily_staff = df.iloc[other_indices, :]

                    st.divider()
                    st.subheader(f"📅 {target_staff} のシフト")
                    st.dataframe(my_daily_shift, hide_index=True)
                    st.subheader("👥 他スタッフの状況")
                    st.dataframe(other_daily_staff, hide_index=True)
                except Exception:
                    st.error("スタッフ行が見つかりません。")
    else:
        # 第一関門不通過
        st.error(f"プログラム停止: {msg}")
        base64_pdf = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')
        st.markdown(f'<embed src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf">', unsafe_allow_html=True)
