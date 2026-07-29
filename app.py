import streamlit as st
import pandas as pd
import pdfplumber

st.title("シフト解析プログラム検証")

# ---------------------------------------------------------
# ③ time_schedule (裏方処理・セッションに保持)
# ---------------------------------------------------------
def load_time_schedule_backend():
    """時程表を読み込み、辞書としてsession_stateに保存する"""
    # 実際はここで共有スプレッドシートから読み込むロジックを実装
    # ここでは検証用に固定の辞書を定義
    schedule = {
        "A": "09:00-18:00", "B": "13:00-22:00", "夜": "22:00-07:00", "休": "公休"
    }
    st.session_state.time_schedule = schedule
    return schedule

if 'time_schedule' not in st.session_state:
    load_time_schedule_backend()

# ---------------------------------------------------------
# メイン画面
# ---------------------------------------------------------
uploaded_pdf = st.file_uploader("シフトPDFをアップロード", type="pdf")

if uploaded_pdf:
    with pdfplumber.open(uploaded_pdf) as pdf:
        # 表の抽出とヘッダー検索（第1関門）
        page = pdf.pages[0]
        table = page.extract_table()
        df_pdf = pd.DataFrame(table)

        # タブで表示を切り替え
        tab1, tab2, tab3 = st.tabs(["① my_daily_shift", "② other_daily_shift", "③ time_schedule"])

        with tab1:
            st.header("① my_daily_shift")
            # PDFから本人行を抽出するロジック（仮）
            st.write("本人用シフトデータを表示します。")
            st.dataframe(df_pdf.head(5)) # デモ用

        with tab2:
            st.header("② other_daily_shift")
            st.write("他スタッフのシフトデータを表示します。")
            st.dataframe(df_pdf.tail(5)) # デモ用

        with tab3:
            st.header("③ time_schedule (検証用)")
            st.info("※通常は画面表示不要な裏方データです")
            st.write(st.session_state.time_schedule)

else:
    st.warning("PDFファイルをアップロードしてください。")
