import streamlit as st
import practice_0 as p0
from googleapiclient.discovery import build
from google.oauth2 import service_account
import calendar

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="シフト・時程 統合管理", layout="wide")
st.title("📅 シフト・時程 統合管理システム")

# セッション管理
if 'stopped' not in st.session_state:
    st.session_state.stopped = False

# --- 1. STOPボタン ---
if st.sidebar.button("🛑 プログラムを停止 (STOP)", type="primary"):
    st.session_state.stopped = True

if st.session_state.stopped:
    st.error("処理を停止しました。最初からやり直すにはブラウザを更新してください。")
    if st.button("再起動"):
        st.session_state.stopped = False
        st.rerun()
    st.stop()

# --- 2. Google認証 ---
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

# --- 3. サイドバー設定 ---
with st.sidebar:
    st.header("1. 解析設定")
    target_staff = st.text_input("スタッフ名", value="西村 文宏")
    uploaded_pdf = st.file_uploader("PDFアップロード", type="pdf")

# --- 4. メイン処理：年月の確認 ---
if uploaded_pdf:
    # 戻り値の数を修正 (y, m の2つ)
    y_guess, m_guess = p0.extract_year_month_from_text(uploaded_pdf.name)
    
    st.subheader("❓ カレンダー情報の確定")
    st.info("ファイル名に年・月が含まれていない場合があります。以下を正しく設定してください。")
    
    col_y, col_m = st.columns(2)
    with col_y:
        final_year = st.number_input("何年のデータですか？", min_value=2024, max_value=2030, value=int(y_guess) if y_guess else 2025)
    with col_m:
        final_month = st.number_input("何月のデータですか？", min_value=1, max_value=12, value=int(m_guess) if m_guess else 3)
    
    # 入力された年月からカレンダー情報を算出
    days_in_month = calendar.monthrange(final_year, final_month)[1]
    first_wd_idx = calendar.monthrange(final_year, final_month)[0]
    wd_names = ["月", "火", "水", "木", "金", "土", "日"]
    
    st.success(f"📌 {final_year}年{final_month}月として処理します。({days_in_month}日間 / 1日は{wd_names[first_wd_idx]}曜日)")

    if drive_service:
        if st.button("2. 解析を実行する", type="primary"):
            with st.spinner("解析中..."):
                time_master_dic = p0.time_schedule_from_drive(drive_service, SHEET_ID)
                pdf_res = p0.pdf_reader(uploaded_pdf, target_staff, days_in_month, time_master_dic)
                
                if isinstance(pdf_res, dict) and "error_type" in pdf_res:
                    if pdf_res["error_type"] == "DAY_MISMATCH":
                        st.error(f"❌ 日程不一致: 設定月は{days_in_month}日ですが、PDFは{pdf_res['act']}日分です。")
                    else:
                        st.error(f"❌ エラー: {pdf_res.get('msg')}")
                    st.stop()

                # 結果表示
                for wp_key, data in pdf_res.items():
                    my_shift, others, original_wp = data
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
