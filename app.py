import streamlit as st
import pandas as pd
import pdfplumber

st.title("シフト解析ダッシュボード")

# 1. タイムスケジュール表
time_schedule_db = {
    "A": "09:00 - 18:00",
    "B": "13:00 - 22:00",
    "夜": "22:00 - 07:00",
    "休": "公休"
}

def process_person_list(df):
    """0列目を解析して(index, 名前)のリストを作成"""
    person_list = []
    for i, val in enumerate(df.iloc[:, 0]):
        val_str = str(val)
        # 空行やnanを「該当なし」として含める
        if pd.isna(val) or val_str.lower() in ['nan', 'none']:
            person_list.append((i, "該当なし"))
        else:
            person_list.append((i, val_str.split('\n')[0].strip()))
    return person_list

uploaded_pdf = st.file_uploader("PDFアップロード", type="pdf")

# 【重要】すべての処理を if uploaded_pdf: の中に配置しました
if uploaded_pdf:
    with pdfplumber.open(uploaded_pdf) as pdf:
        page = pdf.pages[0]
        table = page.extract_table()
        
        if table:
            df_pdf = pd.DataFrame(table)
            
            # 1. 人名リスト作成
            person_list = process_person_list(df_pdf)
            
            # スタッフ選択メニュー
            selected_name = st.selectbox("スタッフを選択", [p[1] for p in person_list])
            
            # 選択された人のindexを取得
            selected_idx = [p[0] for p in person_list if p[1] == selected_name][0]

            # 2. my_daily_shift (本人行＋下段の2行抽出)
            st.write(f"### 1. my_daily_shift ({selected_name} さんのデータ)")
            # 範囲外エラーを防ぐため min(selected_idx + 2, len(df_pdf)) を使用
            my_daily_shift = df_pdf.iloc[selected_idx : min(selected_idx + 2, len(df_pdf)), :]
            st.dataframe(my_daily_shift)

            # 3. other_daily_shift (本人以外の行)
            st.write("### 2. other_daily_shift (本人以外)")
            others = [p[1] for p in person_list if p[1] != selected_name]
            st.write(others)

            # 4. time_schedule 表
            st.write("### 3. time_schedule 表")
            time_df = pd.DataFrame(list(time_schedule_db.items()), columns=["Key", "Time"])
            st.dataframe(time_df)
            
        else:
            st.error("PDFから表データを読み込めませんでした。")
