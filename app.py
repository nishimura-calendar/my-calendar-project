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
    """0列目を解析して人名リストを作成"""
    person_list = []
    has_na_added = False
    i = 0
    # dfの行数分だけループ
    while i < len(df):
        val = str(df.iloc[i, 0])
        
        # 1. Key (T1/T2) があれば「2行スキップ」
        if "T1" in val or "T2" in val:
            i += 2
            continue
        
        # 2. 「該当なし」の処理 (一カ所のみ)
        if pd.isna(df.iloc[i, 0]) or val.lower() in ['nan', 'none', '']:
            if not has_na_added:
                person_list.append((i, "該当なし"))
                has_na_added = True
        else:
            name = val.split('\n')[0].strip()
            person_list.append((i, name))
        i += 1
    return person_list

# -- メイン処理 --
uploaded_pdf = st.file_uploader("PDFアップロード", type="pdf")

if uploaded_pdf:
    with pdfplumber.open(uploaded_pdf) as pdf:
        page = pdf.pages[0]
        table = page.extract_table()
        
        if table:
            # ここで必ず df_pdf を定義
            df_pdf = pd.DataFrame(table)
            
            # リスト作成関数を呼び出し
            person_list = process_person_list(df_pdf)
            
            # スタッフ選択
            names = [p[1] for p in person_list]
            selected_name = st.selectbox("スタッフを選択", names)
            
            # 選択インデックス取得
            selected_idx = [p[0] for p in person_list if p[1] == selected_name][0]
            
            # 表示処理
            st.write(f"### 1. my_daily_shift ({selected_name})")
            my_daily_shift = df_pdf.iloc[selected_idx : selected_idx+2, :]
            st.dataframe(my_daily_shift)
            
            st.write("### 2. other_daily_shift")
            others = [p[1] for p in person_list if p[1] != selected_name]
            st.write(others)
            
            st.write("### 3. Time Schedule 表")
            st.table(pd.DataFrame(list(time_schedule_db.items()), columns=["Key", "Time"]))
        else:
            st.error("表が抽出できませんでした。")
