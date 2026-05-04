import streamlit as st
import practice_0 as p0
import pandas as pd
import base64
import re

# ... (初期設定、認証は前回と同様) ...

uploaded_file = st.file_uploader("PDFファイルをアップロード", type="pdf")

if uploaded_file:
    # --- 年月抽出の判定 (cite: 9) ---
    match = re.search(r'(\d{4})[年\-_](\d{1,2})', uploaded_file.name)
    manual_date = None
    
    # 判別できない場合のみ入力UIを表示 (cite: 9)
    if not match:
        st.info("ファイル名から年月を特定できません。入力してください。")
        col1, col2 = st.columns(2)
        y_in = col1.number_input("年", 2020, 2030, 2026)
        m_in = col2.number_input("月", 1, 12, 1)
        if not st.button("ファイル確認"):
            st.stop()
        manual_date = (y_in, m_in)

    # 抽出成功時はここから自動で次のプロセスへ移行 (cite: 9)
    res, msg = p0.analyze_pdf_structural(uploaded_file, st.session_state.time_dic.keys(), uploaded_file.name, manual_date)

    if res:
        # 第二関門: 拠点チェック
        loc_key = p0.normalize_text(res['location'])
        if loc_key not in st.session_state.time_dic:
            st.error(f"拠点「{res['location']}」は未登録です。")
            st.stop()

        # --- 第三関門: スタッフ選択 (cite: 9) ---
        st.success(f"✅ {res['year']}年{res['month']}月 / 拠点: {res['location']}")
        
        # 誤クリック防止のため初期値を None (index=None) に設定 (cite: 9)
        target_staff = st.selectbox(
            "シフトカレンダーを作成するスタッフを選んで下さい。",
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
                    # my_daily_shift: 本人行 + 下段 (cite: 9)
                    my_daily_shift = df.iloc[idx : idx+2, :]
                    # other_daily_staff: 他人の氏名行のみ (cite: 9)
                    other_indices = [i for i in range(2, len(df), 2) if df.iloc[i, 0] != target_staff]
                    other_daily_staff = df.iloc[other_indices, :]

                    st.divider()
                    st.subheader(f"📅 {target_staff} のシフト")
                    st.dataframe(my_daily_shift, hide_index=True)
                    st.subheader("👥 他スタッフの状況")
                    st.dataframe(other_daily_staff, hide_index=True)
                except Exception:
                    st.error("スタッフ情報の抽出に失敗しました。")
            else:
                st.info("「該当なし」が選択されました。全データを表示します。")
                st.dataframe(df, hide_index=True)
    else:
        st.error(f"プログラム停止: {msg}")
