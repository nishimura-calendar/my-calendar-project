import streamlit as st
import practice_0 as p0

# スプレッドシートID
SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="Schedule Matcher", layout="wide")
st.title("📄 PDF拠点照合 & 時程表表示")

# APIサービスの構築
drive_service, sheets_service = p0.get_unified_services()

if sheets_service:
    # マスターデータをセッション状態に保持
    if 'time_dic' not in st.session_state:
        with st.spinner("スプレッドシートからデータを取得中..."):
            st.session_state.time_dic = p0.time_schedule_from_drive(sheets_service, SHEET_ID)
    
    time_dic = st.session_state.time_dic

    # サイドバー：読込状況の表示
    with st.sidebar:
        st.success(f"マスター読込完了: {len(time_dic)} 拠点")
        with st.expander("登録済みKey一覧"):
            st.write(list(time_dic.keys()))

    # メイン画面：PDFアップロード
    uploaded_pdf = st.file_uploader("勤務表PDFを選択してください", type="pdf")

    if uploaded_pdf and st.button("解析・照合実行", type="primary"):
        result = p0.get_key_and_schedule(uploaded_pdf, time_dic)
        
        if result:
            st.success(f"📍 拠点を特定: {result['key']}")
            st.caption(f"PDF 0列目からの抽出値: {result['raw']}")
            
            # 結果表示
            st.subheader("🕒 該当拠点の時程表")
            st.info("B列は維持、時間列の変換は勤務地行のみ適用されています。")
            st.dataframe(result['time_schedule'], use_container_width=True)
        else:
            st.error("⚠️ 一致する拠点Keyが見つかりませんでした。")
else:
    st.error("認証失敗。secrets.tomlの設定を確認してください。")
