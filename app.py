import streamlit as st
import pandas as pd
import pdfplumber

st.title("シフト解析プログラム")

# --- 初期化・裏方処理 ---
if 'time_schedule' not in st.session_state:
    # ③ time_schedule の元となる辞書
    st.session_state.time_schedule = {"A": "09:00-18:00", "B": "13:00-22:00", "夜": "22:00-07:00", "休": "公休"}

# --- PDFアップロード ---
uploaded_pdf = st.file_uploader("シフト表PDFをアップロード", type="pdf")

if uploaded_pdf:
    with pdfplumber.open(uploaded_pdf) as pdf:
        df_pdf = pd.DataFrame(pdf.pages[0].extract_table())

    # 人名リストの作成ロジック
    # 偶数行を名前行とみなし、リストを作成
    all_indices = range(0, len(df_pdf), 2)
    staff_list = []
    for idx in all_indices:
        name = str(df_pdf.iloc[idx, 0])
        staff_list.append((idx, name if name != 'None' else "該当なし"))

    # ① コンボボックス（セレクトボックス）
    target_staff = st.selectbox("スタッフを選択", [s[1] for s in staff_list])
    target_idx = [s[0] for s in staff_list if s[1] == target_staff][0]

    # --- 3つの表示 ---

    # ① my_daily_shift
    st.header("① my_daily_shift")
    my_df = df_pdf.iloc[target_idx : target_idx + 2, :]
    st.dataframe(my_df)

    # ② other_daily_shift
    st.header("② other_daily_shift")
    others = [s for s in staff_list if s[1] != target_staff]
    other_names = [s[1] for s in others]
    st.write(other_names) # 名前リストを表示

    # ③ time_schedule (ソースの元表を表示)
    st.header("③ time_schedule (Key別一覧)")
    st.table(pd.DataFrame(list(st.session_state.time_schedule.items()), columns=["Key", "内容"]))
