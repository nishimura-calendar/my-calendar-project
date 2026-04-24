import streamlit as st
import math
import practice_0 as p0
import calendar

st.set_page_config(layout="wide", page_title="シフト・時程表統合システム")
st.title("📅 高精度シフト管理システム")

# 共有ID
SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

uploaded_pdf = st.file_uploader("PDFシフト表をアップロード", type="pdf")
target_staff = st.text_input("検索する氏名", value="四村 和義")

if uploaded_pdf and target_staff:
    if st.button("データ解析・統合を開始"):
        # --- (A) 理論上のカレンダー算出 ---
        y_val, m_val = p0.extract_year_month_from_text(uploaded_pdf.name)
        
        if not y_val or not m_val:
            st.error("ファイル名に年月が含まれていません。例: '2026年1月シフト.pdf'")
        else:
            # 理論値(A)
            last_day_A = calendar.monthrange(y_val, m_val)[1]
            first_w_idx = calendar.monthrange(y_val, m_val)[0]
            w_list = ["月", "火", "水", "木", "金", "土", "日"]
            first_weekday_A = w_list[first_w_idx]

            # --- (B) PDF内容の読み取り (打ち合わせの座標定義) ---
            # 巾 l, 高さ h の計算 (整数切り上げ)
            # ※名前の文字数 * 15pt + 余白
            l = math.ceil(max(len("勤務地"), len(target_staff)) * 15) + 10
            h = math.ceil(15.0)
            h_yobi = math.ceil(15.0)

            try:
                # PDF解析実行
                df_pdf = p0.pdf_reader_engine(uploaded_pdf, l)

                if df_pdf is None:
                    st.error("PDFの読み取りに失敗しました。")
                else:
                    # 実測値(B)の抽出
                    # A1セルの右隣(0,1)が日付、その下(2,1)が曜日
                    first_day_B = str(df_pdf.iloc[0, 1]).strip()
                    first_weekday_B = str(df_pdf.iloc[2, 1]).strip()
                    last_day_B = str(df_pdf.iloc[0, -1]).strip()

                    # --- 検問 A != B なら終了 ---
                    if str(last_day_A) != last_day_B or first_weekday_A not in first_weekday_B:
                        st.error("❌ 検問不合格: ファイル名と内容のカレンダーが一致しません。")
                        st.write(f"理論(A): {last_day_A}日/{first_weekday_A}曜")
                        st.write(f"実測(B): {last_day_B}日/{first_weekday_B}曜")
                        st.stop()
                    
                    st.success(f"✅ 検問合格: {y_val}年{m_val}月（{last_day_A}日間）")

                    # --- データ統合フェーズ ---
                    # ① 時程表の取得 (勤務地が「正」となるマスター)
                    time_schedule_dic = p0.time_schedule_from_drive(SHEET_ID)

                    # ② シフトの抽出と統合 (data_integration)
                    final_data = p0.data_integration(df_pdf, time_schedule_dic, target_staff)

                    # 結果の表示
                    if not final_data:
                        st.warning("統合可能なデータが見つかりませんでした。時程表の勤務地名を確認してください。")
                    for loc, data in final_data.items():
                        st.divider()
                        st.subheader(f"📍 拠点: {loc}")
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write("【個人シフト (my_daily_shift)】")
                            st.dataframe(data["my_daily_shift"])
                        with col2:
                            st.write("【時程表 (time_schedule)】")
                            st.dataframe(data["time_schedule"])
                        st.write("【他スタッフ (other_daily_shift)】")
                        st.dataframe(data["other_daily_shift"])

            except Exception as e:
                st.error(f"システムエラー: {e}")
