import streamlit as st
import pandas as pd
import pdfplumber

st.title("シフトデータ確認用ダッシュボード")

uploaded_pdf = st.file_uploader("シフト表PDFをアップロード", type="pdf")

# (簡易的な時間データ - 実際はPDFから読み取るか別途用意したリスト)
time_schedule_db = {
    "A": "09:00 - 18:00",
    "B": "13:00 - 22:00",
    "夜": "22:00 - 07:00",
    "休": "公休"
}

if uploaded_pdf:
    with pdfplumber.open(uploaded_pdf) as pdf:
        df_pdf = pd.DataFrame(pdf.pages[0].extract_table())
        
        # 名前リスト作成（ロジックは前回同様）
        names_list = []
        for i, row in df_pdf.iterrows():
            val = str(row[0]).strip()
            if len(val) >= 2 and "T1" not in val:
                names_list.append((i, val.split('\n')[0]))

        selected_name = st.selectbox("確認したいスタッフを選択", [n[1] for n in names_list])
        idx = [n[0] for n in names_list if n[1] == selected_name][0]

        # 1. my_daily_shift (本人・2行)
        st.write("### 1. my_daily_shift (本人行＋下段の2行)")
        my_daily_shift = df_pdf.iloc[idx:idx+2, :]
        st.dataframe(my_daily_shift)

        # 2. other_daily_shift (他者・名前行のみ)
        st.write("### 2. other_daily_shift (他者一覧)")
        others = [n[1] for n in names_list if n[1] != selected_name]
        st.write(others)

        # 3. time_schedule (Key検索機能)
        st.write("### 3. time_schedule (シフト記号検索)")
        search_key = st.text_input("シフト記号を入力 (例: A, B, 夜, 休)")
        if search_key:
            result = time_schedule_db.get(search_key.upper(), "該当なし")
            st.write(f"検索結果: **{search_key}** → {result}")
