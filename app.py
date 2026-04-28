import streamlit as st
import practice_0 as p0

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="時程表設定確認と解析", layout="wide")
st.title("🛡️ 時程表設定確認 ＆ シフト照合システム")

drive_service, sheets_service = p0.get_unified_services()

if sheets_service:
    # 1. データの読み込み
    with st.spinner("スプレッドシートを読み込み中..."):
        time_dic = p0.time_schedule_from_drive(sheets_service, SHEET_ID)

    # 2. 【停止ステップ】時程表の全Keyとスケジュールの表示
    st.header("📊 Step 1: 時程表マスターの確認")
    st.info("以下の各拠点設定が正しいか確認してください。時間は「6:15」形式に変換されています。")
    
    for key, df in time_dic.items():
        with st.expander(f"拠点Key: {key}", expanded=True):
            st.dataframe(df, use_container_width=True)

    # 確認チェックボックス（これにチェックを入れないと解析できないようにする）
    confirmed = st.checkbox("上記マスターデータの内容が正しいことを確認しました。")

    if not confirmed:
        st.warning("⚠️ 内容を確認し、上のチェックボックスをオンにすると解析メニューが表示されます。")
        st.stop()

    # 3. 解析ステップ
    st.divider()
    st.header("🔍 Step 2: PDF解析と照合")
    
    col1, col2 = st.columns([1, 2])
    with col1:
        target_staff = st.text_input("解析対象者名", value="西村 文宏")
        uploaded_pdf = st.file_uploader("勤務表PDFをアップロード", type="pdf")
        run_analysis = st.button("解析・照合を実行")

    if run_analysis:
        if uploaded_pdf and target_staff:
            results, error = p0.pdf_reader_final(uploaded_pdf, target_staff, time_dic)
            if error:
                st.error(f"🛑 停止（第1〜3関門）: {error}")
                st.stop()
            
            for res in results:
                st.success(f"✅ 拠点「{res['key']}」との照合に成功しました")
                st.dataframe(res['my_data'])
                with st.expander("適用された時程表"):
                    st.dataframe(res['time_range'])
