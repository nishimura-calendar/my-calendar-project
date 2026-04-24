import streamlit as st
import math
import practice_0 as p0
import calendar
import re

st.set_page_config(layout="wide", page_title="シフト・時程表統合システム")
st.title("📅 高精度シフト管理システム (再構築モード)")

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

uploaded_pdf = st.file_uploader("PDFシフト表をアップロード", type="pdf")
target_staff = st.text_input("検索する氏名", value="四村 和義")

if uploaded_pdf and target_staff:
    # --- (A) 理論値の算出 ---
    y_val, m_val = p0.extract_year_month_from_text(uploaded_pdf.name)
    last_day_theory = calendar.monthrange(y_val, m_val)[1]
    first_w_idx = calendar.monthrange(y_val, m_val)[0]
    w_list = ["月", "火", "水", "木", "金", "土", "日"]
    weekday_theory = w_list[first_w_idx]

    # --- (B) PDFの解析 ---
    l = math.ceil(max(len("勤務地"), len(target_staff)) * 15) + 15
    df_pdf = p0.pdf_reader_engine(uploaded_pdf, l)

    if df_pdf is not None:
        st.subheader("1. 検問（ファイル名との照合）")
        
        # 柔軟な抽出ロジックで実測値を取得
        last_day_actual, detected_loc = p0.get_actual_info(df_pdf, SHEET_ID)
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("末日の判定", f"{last_day_actual}日", f"理論値: {last_day_theory}日", delta_color="normal")
        with col2:
            st.metric("検出された勤務地", f"{detected_loc}")

        # 検問判定
        if int(last_day_theory) == int(last_day_actual):
            st.success(f"✅ 検問合格: {y_val}年{m_val}月のデータとして正しく認識されました。")
            
            if st.button("このまま勤務表を再構築する"):
                # 統合・再構築の実行
                results = p0.rebuild_shift_data(df_pdf, SHEET_ID, target_staff, detected_loc)
                
                if results:
                    st.divider()
                    st.subheader(f"📍 再構築完了: {detected_loc}")
                    st.write("【あなたのシフト】")
                    st.dataframe(results["my_shift"])
                    st.write("【適用される時程マスター】")
                    st.dataframe(results["time_master"])
                else:
                    st.error("データの抽出に失敗しました。氏名が正しいか確認してください。")
        else:
            st.error("❌ 検問不合格: PDF内の日数とファイル名が一致しません。")
            st.write("解析された表の構造:", df_pdf.head(3))
