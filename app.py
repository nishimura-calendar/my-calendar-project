import streamlit as st
import math
import practice_0 as p0
import calendar

st.set_page_config(layout="wide", page_title="シフト・時程表統合システム")
st.title("📅 高精度シフト管理システム")

# 固定の時程表スプレッドシートID
SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

uploaded_pdf = st.file_uploader("PDFシフト表をアップロード", type="pdf")
target_staff = st.text_input("検索する氏名", value="四村 和義")

if uploaded_pdf and target_staff:
    # --- (A) 理論上のカレンダー算出 ---
    y_val, m_val = p0.extract_year_month_from_text(uploaded_pdf.name)
    if not y_val or not m_val:
        st.error("ファイル名から年月を特定できません。例: '2026年1月.pdf'")
    else:
        last_day_A = calendar.monthrange(y_val, m_val)[1]
        first_w_idx = calendar.monthrange(y_val, m_val)[0]
        w_list = ["月", "火", "水", "木", "金", "土", "日"]
        first_weekday_A = w_list[first_w_idx]

        # --- (B) PDFのDataFrame変換 ---
        # 巾 l の計算 (整数切り上げ)
        l = math.ceil(max(len("勤務地"), len(target_staff)) * 15) + 10
        df_pdf = p0.pdf_reader_engine(uploaded_pdf, l)

        if df_pdf is not None:
            st.subheader("1. 解析データの検問")
            
            # 住所指定によるデータ抽出
            # 日付[0, -1], 曜日[1, 1], 勤務地[1, 0]
            last_day_B = str(df_pdf.iloc[0, -1]).strip()
            first_weekday_B = str(df_pdf.iloc[1, 1]).strip()
            detected_loc = str(df_pdf.iloc[1, 0]).strip()

            # 検問結果の表示
            col_a, col_b = st.columns(2)
            with col_a:
                st.write(f"**理論値(A)**: {last_day_A}日 / {first_weekday_A}曜日")
            with col_b:
                st.write(f"**実測値(B)**: {last_day_B}日 / {first_weekday_B}曜日")

            if str(last_day_A) != last_day_B or first_weekday_A not in first_weekday_B:
                st.error("❌ カレンダー情報が不一致です。")
                st.dataframe(df_pdf.head(3)) # 構造確認用
            else:
                st.success(f"✅ 検問合格: {detected_loc}拠点")

            # ユーザー確認と実行
            st.divider()
            st.subheader("2. データの統合実行")
            st.info(f"抽出された勤務地: **{detected_loc}** として、時程表と紐付けます。")
            
            if st.button("この内容で時程表と統合する"):
                # ① 時程表(Master)取得
                time_schedule_dic = p0.time_schedule_from_drive(SHEET_ID)
                # ② 統合
                final_data = p0.data_integration_v2(df_pdf, time_schedule_dic, target_staff, detected_loc)

                if final_data:
                    for loc, data in final_data.items():
                        st.success(f"拠点「{loc}」の統合が完了しました。")
                        st.write("【個人シフト】", data["my_daily_shift"])
                        st.write("【時程表】", data["time_schedule"])
                        st.write("【全体シフト】", data["other_daily_shift"])
                else:
                    st.error("時程表の勤務地名と一致しなかったため、統合を中断しました。")
