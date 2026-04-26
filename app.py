import streamlit as st
import practice_0 as p0
from googleapiclient.discovery import build
from google.oauth2 import service_account
import calendar

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="シフト・時程 統合管理", layout="wide")
st.title("📅 シフト・時程 統合管理システム")

# セッション状態で停止フラグを管理
if 'stopped' not in st.session_state:
    st.session_state.stopped = False

# --- サイドバー：停止ボタン ---
if st.sidebar.button("🛑 プログラムを停止 (STOP)", type="primary"):
    st.session_state.stopped = True

if st.session_state.stopped:
    st.error("STOPボタンが押されました。処理を中断しています。")
    if st.button("入力をやり直す"):
        st.session_state.stopped = False
        st.rerun()
    st.stop()

# --- Google認証 ---
@st.cache_resource
def get_drive_service():
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

drive_service = get_drive_service()

# --- サイドバー：入力 ---
with st.sidebar:
    st.header("1. 解析設定")
    target_staff = st.text_input("スタッフ名", value="西村 文宏")
    uploaded_pdf = st.file_uploader("PDFファイルをアップロード", type="pdf")

# --- メイン：対話型確認エリア ---
if uploaded_pdf:
    # 戻り値の数を修正 (y, m のみ受け取る)
    y_guess, m_guess = p0.extract_year_month_from_text(uploaded_pdf.name)
    
    st.info("📂 ファイルを検知しました。カレンダー情報を確定させてください。")
    
    if not y_guess or not m_guess:
        st.warning("⚠️ ファイル名から年・月が特定できません。以下を正しく設定してください。")
    
    col_y, col_m = st.columns(2)
    with col_y:
        final_year = st.number_input("何年のデータですか？", min_value=2024, max_value=2030, value=int(y_guess) if y_guess else 2025)
    with col_m:
        final_month = st.number_input("何月のデータですか？", min_value=1, max_value=12, value=int(m_guess) if m_guess else 3)
    
    # ユーザー入力に基づきカレンダー情報を確定
    days_in_month = calendar.monthrange(final_year, final_month)[1]
    first_wd_idx = calendar.monthrange(final_year, final_month)[0]
    wd_names = ["月", "火", "水", "木", "金", "土", "日"]
    
    st.success(f"📌 {final_year}年{final_month}月として処理します。({days_in_month}日間 / 1日は{wd_names[first_wd_idx]}曜日)")

    if drive_service:
        if st.button("2. 解析を実行する", type="primary"):
            with st.spinner("解析中..."):
                # 時程表読み込み
                time_master_dic = p0.time_schedule_from_drive(drive_service, SHEET_ID)
                # PDF解析 (ユーザー確定の日数を使用)
                pdf_res = p0.pdf_reader(uploaded_pdf, target_staff, days_in_month, time_master_dic)
                
                if isinstance(pdf_res, dict) and "error_type" in pdf_res:
                    if pdf_res["error_type"] == "DAY_MISMATCH":
                        st.error(f"❌ 日程不一致: 指定された月は{days_in_month}日ですが、PDFは{pdf_res['act']}日分です。年月の設定が正しいか確認してください。")
                    else:
                        st.error(f"❌ エラー: {pdf_res.get('msg', '解析に失敗しました')}")
                    st.stop()

                # 結果表示
                for wp_key, data in pdf_res.items():
                    my_shift, others, original_wp = data
                    st.balloons()
                    st.success(f"✅ 全関門突破: {original_wp}")
                    st.divider()
                    st.header(f"📍 勤務地: {original_wp}")
                    
                    st.subheader("👤 自分のシフト")
                    st.dataframe(my_shift, use_container_width=True)
                    
                    st.subheader("👥 他スタッフ")
                    st.dataframe(others, use_container_width=True)
                    
                    st.subheader("🕒 時程表")
                    st.dataframe(time_master_dic[wp_key]["df"], use_container_width=True)
else:
    st.write("サイドバーからPDFファイルをアップロードしてください。")
