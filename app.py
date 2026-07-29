import streamlit as st
import pandas as pd
import numpy as np

st.title("シフト解析ダッシュボード")

# 1. タイムスケジュール表（辞書で管理）
time_schedule_db = {
    "A": "09:00 - 18:00",
    "B": "13:00 - 22:00",
    "夜": "22:00 - 07:00",
    "休": "公休"
}
time_df = pd.DataFrame(list(time_schedule_db.items()), columns=["Key", "Time"])

def process_person_list(df):
    """0列目を解析して(index, 名前)のリストを作成"""
    person_list = []
    for i, val in enumerate(df.iloc[:, 0]):
        val_str = str(val)
        # 空行、nan、T1/T2を「該当なし」として扱う
        if pd.isna(val) or val_str.lower() in ['nan', 'none', 't1', 't2']:
            person_list.append((i, "該当なし"))
        else:
            person_list.append((i, val_str.split('\n')[0].strip()))
    return person_list

# -- 以下、メイン処理 --
uploaded_pdf = st.file_uploader("PDFアップロード", type="pdf")

if uploaded_pdf:
    # (ここでは df_pdf を読み込んだものと仮定)
    # ... df_pdf 読み込み処理 ...
    
    # 1. リスト作成
    person_list = process_person_list(df_pdf)
    
    # 選択メニュー
    selected_name_name = st.selectbox("スタッフを選択", [p[1] for p in person_list])
    selected_idx = [p[0] for p in person_list if p[1] == selected_name_name][0]

    # 2. 人名行（2行分）の抽出表
    st.write(f"### {selected_name_name} さんのデータ抽出")
    person_data = df_pdf.iloc[selected_idx:selected_idx+2, :]
    st.dataframe(person_data)

    # 3. Time_Schedule 表の表示
    st.write("### Time Schedule 表")
    st.dataframe(time_schedule_db)
