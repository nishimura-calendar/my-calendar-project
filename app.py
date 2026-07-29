import streamlit as st
import pandas as pd

st.title("シフト解析ダッシュボード")

# 1. タイムスケジュール表の定義
time_schedule_db = {
    "A": "09:00 - 18:00",
    "B": "13:00 - 22:00",
    "夜": "22:00 - 07:00",
    "休": "公休"
}

def process_person_list(df):
    """0列目を解析して(index, 名前)のリストを作成"""
    person_list = []
    i = 0
    while i < len(df):
        val = str(df.iloc[i, 0])
        
        # 1. Key (T1/T2) があれば「2行スキップ」
        if "T1" in val or "T2" in val:
            i += 2
            continue
        
        # 2. 「該当なし (nan)」の処理
        if pd.isna(df.iloc[i, 0]) or val.lower() in ['nan', 'none']:
            # リストが空でない、かつ直前が「該当なし」でなければ追加（1カ所だけに制限）
            if not person_list or person_list[-1][1] != "該当なし":
                person_list.append((i, "該当なし"))
        else:
            # 名前を抽出
            name = val.split('\n')[0].strip()
            person_list.append((i, name))
        i += 1
    return person_list

# -- メイン処理 --
uploaded_pdf = st.file_uploader("PDFアップロード", type="pdf")

if uploaded_pdf:
    # (ここではPDF解析結果を df_pdf に格納していると仮定します)
    # df_pdf = ... (前回までのコードと同じ処理)

    # 人名リスト作成
    person_list = process_person_list(df_pdf)
    
    # 選択メニュー
    selected_name = st.selectbox("スタッフを選択", [p[1] for p in person_list])
    
    # 選択した人の index を取得
    selected_idx = [p[0] for p in person_list if p[1] == selected_name][0]

    # --- 表示エリア ---
    
    # 1. my_daily_shift (本人行＋下段の計2行)
    st.write(f"### 1. my_daily_shift ({selected_name})")
    my_daily_shift = df_pdf.iloc[selected_idx : selected_idx+2, :]
    st.dataframe(my_daily_shift)

    # 2. other_daily_shift (本人以外)
    st.write("### 2. other_daily_shift (他者リスト)")
    others = [p[1] for p in person_list if p[1] != selected_name]
    st.write(others)

    # 3. time_schedule 表 (データフレーム化して表示)
    st.write("### 3. Time Schedule 表")
    time_df = pd.DataFrame(list(time_schedule_db.items()), columns=["Key", "Time"])
    st.table(time_df)
