import streamlit as st
import practice_0 as p0

# 定数
SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="Key & TimeSchedule Viewer", layout="wide")
st.title("📄 PDF拠点照合 & 時程表表示")

# practice_0 から認証関数を呼び出し
drive_service, sheets_service = p0.get_unified_services()

if sheets_service:
    # マスターデータをセッションに保持
    if 'time_dic' not in st.session_state:
        with st.spinner("マスターデータを読み込み中..."):
            st.session_state.time_dic = p0.time_schedule_from_drive(sheets_service, SHEET_ID)
    
    time_dic = st.session_state.time_dic

    # サイドバー：登録済みKeyの確認
    with st.sidebar:
        st.success(f"マスター読込済み: {len(time_dic)} 拠点")
        with st.expander("登録済みKey一覧"):
            st.write(list(time_dic.keys()))

    # ファイルアップロード
    uploaded_pdf = st.file_uploader("勤務表PDFをアップロード", type="pdf")

    if uploaded_pdf:
        if st.button("解析・照合実行", type="primary"):
            result = p0.get_key_and_schedule(uploaded_pdf, time_dic)
            
            if result:
                st.success(f"📍 特定された拠点: {result['key']}")
                st.caption(f"PDF座標[0,0]の取得値: {result['raw']}")
                
                # 時程表の表示
                st.subheader("🕒 該当拠点の時程表 (A-C列 + 時間軸)")
                st.dataframe(result['time_schedule'], use_container_width=True)
            else:
                st.error("⚠️ 拠点を特定できませんでした。PDFの表記とマスターのKey(A列)が一致するか確認してください。")
else:
    st.error("Google API認証に失敗しました。secrets.tomlの設定を確認してください。")
