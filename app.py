import streamlit as st
import practice_0 as p0

# ユーザー指定のスプレッドシートIDを固定
SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.title("📅 シフト解析・紐付け確認画面")

# サイドバー設定
with st.sidebar:
    target_staff = st.text_input("解析する名前", value="西村 文宏")
    uploaded_pdf = st.file_uploader("PDFアップロード", type="pdf")

if target_staff and uploaded_pdf:
    if st.button("解析実行"):
        # 1. PDFから自分のシフト、他人のシフト、勤務地を抽出
        # 内部で header[len(header)//2] を勤務地として特定
        pdf_results, year, month, consistency_report = p0.pdf_reader(uploaded_pdf, target_staff, uploaded_pdf.name)
        
        # 2. 指定されたスプレッドシートから時程表データを取得
        # serviceオブジェクトは認証済みと仮定
        if 'g_service' in st.session_state and st.session_state.g_service:
            service = st.session_state.g_service
            time_dic = p0.time_schedule_from_drive(service, SHEET_ID)
            
            # 3. 紐付けと表示
            if pdf_results:
                st.success(f"🔍 解析対象: {year}年{month}月")
                
                for work_place, data in pdf_results.items():
                    st.divider()
                    st.header(f"📍 勤務地: {work_place}")
                    
                    # 紐付け確認 (PDFの勤務地 vs 時程表A列の勤務地)
                    matched_time_sched = None
                    for t_key, t_df in time_dic.items():
                        if p0.normalize_text(work_place) == p0.normalize_text(t_key):
                            matched_time_sched = t_df
                            break
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.subheader("🟢 my_daily_shift")
                        st.dataframe(data[0])
                    with col2:
                        st.subheader("👥 other_daily_shift")
                        st.dataframe(data[1])
                    
                    st.subheader(f"🕒 time_schedule (紐付け先: {work_place})")
                    if matched_time_sched is not None:
                        st.dataframe(matched_time_sched)
                        # ここで「辞書登録」を確認事項として保持
                        st.info(f"✅ {work_place} の紐付けに成功しました。")
                    else:
                        st.error(f"⚠️ 時程表に '{work_place}' が見つかりません。")
        else:
            st.error("Google Driveへの接続（認証）が必要です。")
