import streamlit as st
import practice_0 as p0
import pandas as pd

# (認証設定などは省略)

st.title("📅 シフト解析・紐付け確認画面")

with st.sidebar:
    target_staff = st.text_input("解析する名前", value="西村 文宏")
    uploaded_pdf = st.file_uploader("PDFアップロード", type="pdf")
    # sheet_id は secrets 等から取得
    sheet_id = st.secrets.get("sheet_id", "YOUR_DEFAULT_ID")

if target_staff and uploaded_pdf:
    if st.button("解析実行"):
        # 1. PDF解析 (整合性チェック含む)
        pdf_results, year, month, consistency_report = p0.pdf_reader(uploaded_pdf, target_staff, uploaded_pdf.name)
        
        # 2. 時程表の取得
        # ※ service オブジェクトは認証済みと仮定
        try:
            time_dic = p0.time_schedule_from_drive(service, sheet_id)
        except Exception as e:
            st.error(f"時程表の取得に失敗しました: {e}")
            time_dic = {}

        # 3. 整合性エラーの報告 (不一致ならここで詳細を表示)
        if consistency_report:
            for place, report in consistency_report.items():
                st.error(f"❌ 【{place}】 整合性不一致")
                st.warning(f"理由: {report['reason']}")
                with st.expander("PDFの生データを確認（不一致時のみ）"):
                    st.dataframe(report['df'])
            
            if not pdf_results:
                st.stop() # 正常なデータが1つもなければ停止

        # 4. 紐付けの確認 (これが絶対の守り事項)
        if pdf_results:
            st.success(f"🔍 解析対象: {year}年{month}月")
            
            for work_place, data in pdf_results.items():
                st.divider()
                st.header(f"📍 勤務地: {work_place}")
                
                # PDFの場所名と時程表の場所名を紐付け
                # normalize_text を通して比較
                matched_time_sched = None
                for t_key, t_df in time_dic.items():
                    if p0.normalize_text(work_place) in p0.normalize_text(t_key):
                        matched_time_sched = t_df
                        break
                
                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("🟢 my_daily_shift")
                    st.dataframe(data[0], use_container_width=True)
                
                with col2:
                    st.subheader("👥 other_daily_shift")
                    st.dataframe(data[1], use_container_width=True)
                
                st.subheader(f"🕒 time_schedule (紐付け先: {work_place})")
                if matched_time_sched is not None:
                    st.dataframe(matched_time_sched, use_container_width=True)
                else:
                    st.error(f"時程表の中に '{work_place}' に該当する勤務地データが見つかりません。")
                    st.info(f"現在の時程表内キー: {list(time_dic.keys())}")

            # 5. 全て一致していれば解析へ進む (final_rows生成)
            # data_to_process = {place: [pdf[0], pdf[1], time_dic[matched]] ... }
            # ... 後続のCSV生成処理 ...
