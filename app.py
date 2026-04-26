import streamlit as st
import practice_0 as p0
# ... (認証部分は前回同様) ...

if sheets_service:
    try:
        # 時程表（マスター）取得
        time_dic = p0.time_schedule_from_drive(sheets_service, SHEET_ID)
        master_keys = list(time_dic.keys())
    except Exception as e:
        st.error(f"❌ スプレッドシート取得失敗: {e}")
        st.stop()

    if target_staff and uploaded_pdf:
        if st.button("解析実行"):
            y, m, exp_days, exp_wd = p0.extract_year_month_from_text(uploaded_pdf.name)
            
            # PDF解析（マスターのキー一覧を渡してチェック）
            pdf_res = p0.pdf_reader(uploaded_pdf, target_staff, exp_days, master_keys)
            
            if isinstance(pdf_res, dict) and "error_type" in pdf_res:
                if pdf_res["error_type"] == "WP_MISSING":
                    st.error(f"❌ 第1関門突破失敗：PDF内の勤務地『{pdf_res['wp']}』は、時程表（マスター）に登録されていません。")
                elif pdf_res["error_type"] == "DAY_MISMATCH":
                    st.error(f"❌ 第2関門突破失敗：日程が一致しません。ファイル名は{pdf_res['exp']}日分ですが、PDFは{pdf_res['act']}日分あります。")
                st.stop()

            # --- 第三関門（紐付け表示） ---
            for wp_key, data in pdf_res.items():
                my_shift, others, original_wp = data
                st.success(f"✅ 全関門突破: {original_wp}")
                st.divider()
                
                st.subheader(f"🕒 time_schedule (時程表: {original_wp})")
                st.dataframe(time_dic[wp_key])
                
                st.subheader(f"👤 my_daily_shift (自分のシフト)")
                st.dataframe(my_shift)
                
                st.subheader(f"👥 other_daily_shift (他スタッフ)")
                st.dataframe(others)
