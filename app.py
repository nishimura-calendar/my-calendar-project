import streamlit as st
import practice_0 as p0
from googleapiclient.discovery import build
import calendar

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="シフト・時程 統合管理", layout="wide")
st.title("📅 シフト・時程 統合管理システム")

# セッション状態の初期化
if 'process_stopped' not in st.session_state:
    st.session_state.process_stopped = False

# STOPボタンが押された場合の処理
if st.sidebar.button("🛑 プログラムを停止 (STOP)", type="secondary"):
    st.session_state.process_stopped = True
    st.warning("処理を停止しました。最初からやり直すにはページをリロードしてください。")

if st.session_state.process_stopped:
    st.stop()

@st.cache_resource
def get_unified_services():
    # ... (認証処理は以前と同様)
    return build('drive', 'v3', credentials=creds)

drive_service = get_unified_services()

with st.sidebar:
    st.header("1. 基本情報の入力")
    target_staff = st.text_input("解析する名前", value="西村 文宏")
    uploaded_pdf = st.file_uploader("PDFアップロード", type="pdf")

if uploaded_pdf:
    # ファイル名から暫定的に年・月を抽出
    y_guess, m_guess, _, _ = p0.extract_year_month_from_text(uploaded_pdf.name)
    
    st.info("💡 ファイル名から解析した情報です。正しくない場合は修正してください。")
    col_y, col_m = st.columns(2)
    with col_y:
        selected_year = st.number_input("対象年", min_value=2020, max_value=2030, value=int(y_guess) if y_guess else 2025)
    with col_m:
        selected_month = st.number_input("対象月", min_value=1, max_value=12, value=int(m_guess) if m_guess else 3)
    
    # 確定した年・月から第一曜日を計算
    days_in_month = calendar.monthrange(selected_year, selected_month)[1]
    first_wd_idx = calendar.monthrange(selected_year, selected_month)[0]
    wd_names = ["月", "火", "水", "木", "金", "土", "日"]
    st.success(f"📅 確定条件: {selected_year}年{selected_month}月 ({days_in_month}日間 / 1日は{wd_names[first_wd_idx]}曜日)")

if drive_service and not st.session_state.process_stopped:
    try:
        time_master_dic = p0.time_schedule_from_drive(drive_service, SHEET_ID)
    except Exception as e:
        st.error(f"❌ マスター取得失敗: {e}")
        st.stop()

if uploaded_pdf and not st.session_state.process_stopped:
    if st.button("2. 解析を実行する", type="primary"):
        # pdf_readerにユーザーが指定した日数と第一曜日を渡す
        pdf_res = p0.pdf_reader(uploaded_pdf, target_staff, days_in_month, time_master_dic)
        
        # ... (結果表示ロジックは以前と同様)
