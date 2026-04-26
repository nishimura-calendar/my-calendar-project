import streamlit as st
import practice_0 as p0
from googleapiclient.discovery import build
from google.oauth2 import service_account
import calendar

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="シフト・時程 統合管理", layout="wide")
st.title("📅 シフト・時程 統合管理システム")

# セッション状態の初期化
if 'process_stopped' not in st.session_state:
    st.session_state.process_stopped = False

# --- 1. STOPボタン (最優先) ---
if st.sidebar.button("🛑 プログラムを停止 (STOP)", type="primary"):
    st.session_state.process_stopped = True

if st.session_state.process_stopped:
    st.warning("処理を中断しました。再開するにはブラウザを更新してください。")
    if st.button("最初からやり直す"):
        st.session_state.process_stopped = False
        st.rerun()
    st.stop()

# --- 2. Googleサービス接続 ---
@st.cache_resource
def get_unified_services():
    try:
        if "gcp_service_account" in st.secrets:
            info = st.secrets["gcp_service_account"]
            creds = service_account.Credentials.from_service_account_info(
                info, scopes=["https://www.googleapis.com/auth/drive.readonly"]
            )
            return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"認証エラー: {e}")
    return None

drive_service = get_unified_services()

# --- 3. ユーザー入力エリア ---
with st.sidebar:
    st.header("設定")
    target_staff = st.text_input("解析する名前", value="西村 文宏")
    uploaded_pdf = st.file_uploader("PDFアップロード", type="pdf")

if uploaded_pdf:
    # ファイル名から取得を試みるが、不確実なためユーザーに確認させる
    y_guess, m_guess, _, _ = p0.extract_year_month_from_text(uploaded_pdf.name)
    
    st.markdown("---")
    st.subheader("❓ カレンダー情報の確認")
    st.warning("ファイル名に年・月が不足している場合があります。正しい情報を入力してください。")
    
    col_y, col_m = st.columns(2)
    with col_y:
        # y_guessがNoneなら2025を初期値に
        input_year = st.number_input("何年のデータですか？", min_value=2024, max_value=2030, value=int(y_guess) if y_guess else 2025)
    with col_m:
        input_month = st.number_input("何月のデータですか？", min_value=1, max_value=12, value=int(m_guess) if m_guess else 3)
    
    # ユーザー入力に基づきカレンダーを確定
    days_in_month = calendar.monthrange(input_year, input_month)[1]
    first_wd_idx = calendar.monthrange(input_year, input_month)[0]
    wd_names = ["月", "火", "水", "木", "金", "土", "日"]
    
    st.info(f"💡 確認済み: {input_year}年{input_month}月は「{wd_names[first_wd_idx]}曜日」から始まり、{days_in_month}日間あります。")

# --- 4. 解析実行 ---
if drive_service and uploaded_pdf and not st.session_state.process_stopped:
    if st.button("解析を実行する", type="primary"):
        with st.spinner("解析中..."):
            # 時程表（マスター）取得
            time_master_dic = p0.time_schedule_from_drive(drive_service, SHEET_ID)
            
            # PDF解析（ユーザーが確定させた日数を使用）
            pdf_res = p0.pdf_reader(uploaded_pdf, target_staff, days_in_month, time_master_dic)
            
            if isinstance(pdf_res, dict) and "error_type" in pdf_res:
                st.error("関門突破失敗")
                if pdf_res["error_type"] == "WP_MISSING":
                    st.error("勤務地が見つかりません。")
                elif pdf_res["error_type"] == "DAY_MISMATCH":
                    st.error(f"日程が一致しません。入力:{days_in_month}日に対してPDFは{pdf_res['act']}日分あります。")
                st.stop()

            # 結果表示
            for wp_key, data in pdf_res.items():
                my_shift, others, original_wp = data
                st.success(f"✅ 全関門突破: {original_wp}")
                st.divider()
                st.subheader(f"📍 勤務地: {original_wp}")
                st.write("👤 自分のシフト")
                st.dataframe(my_shift)
                st.write("👥 他スタッフ")
                st.dataframe(others)
                st.write("🕒 時程表")
                st.dataframe(time_master_dic[wp_key]["df"])
