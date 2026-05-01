import streamlit as st
import practice_0 as p0

# スプレッドシートID
SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="PDF Schedule Matcher", layout="wide")
st.title("📄 PDF拠点照合 & 時程表表示")

# APIサービスの取得
drive_service, sheets_service = p0.get_unified_services()

if sheets_service:
    # マスターデータをセッションに保持（初回のみ取得）
    if 'time_dic' not in st.session_state:
        with st.spinner("スプレッドシートからマスターデータを読み込み中..."):
            st.session_state.time_dic = p0.time_schedule_from_drive(sheets_service, SHEET_ID)
    
    time_dic = st.session_state.time_dic

    # サイドバー：読込状況
    with st.sidebar:
        st.success(f"読込完了: {len(time_dic)} 拠点")
        with st.expander("登録済み勤務地Key一覧"):
            st.write(list(time_dic.keys()))

    # メイン：PDFアップロード
    uploaded_pdf = st.file_uploader("勤務予定表（PDF）を選択してください", type="pdf")

    if uploaded_pdf and st.button("解析・照合を実行", type="primary"):
        result = p0.get_key_and_schedule(uploaded_pdf, time_dic)
        
        if result:
            st.success(f"📍 特定拠点: {result['key']}")
            st.caption(f"PDFからの抽出文字列: {result['raw']}")
            
            # 結果表示
            st.subheader("🕒 拠点の時程表")
            st.info("B列は維持、時間変換は勤務地行（見出し）のみ適用されています。")
            st.dataframe(result['time_schedule'], use_container_width=True)
        else:
            st.error("⚠️ PDFの0列目に一致する勤務地Keyが見つかりませんでした。")
else:
    st.error("Google API認証に失敗しました。secretsの設定を確認してください。")
