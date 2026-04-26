import streamlit as st
import practice_0 as p0
from googleapiclient.discovery import build
from google.oauth2 import service_account
import calendar

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="シフト・時程 統合管理", layout="wide")
st.title("📅 シフト・時程 統合管理システム")

if 'stopped' not in st.session_state: st.session_state.stopped = False

# --- STOPボタン ---
if st.sidebar.button("🛑 プログラムを停止 (STOP)", type="primary"):
    st.session_state.stopped = True

if st.session_state.stopped:
    st.error("停止中。再開するにはブラウザを更新してください。")
    st.stop()

@st.cache_resource
def get_drive_service():
    if "gcp_service_account" in st.secrets:
        info = st.secrets["gcp_service_account"]
        creds = service_account.Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/drive.readonly"])
        return build('drive', 'v3', credentials=creds)
    return None

drive_service = get_drive_service()

# --- 入力エリア ---
with st.sidebar:
    st.header("1. 解析設定")
    target_staff = st.text_input("スタッフ名", value="西村 文宏")
    uploaded_pdf = st.file_uploader("PDFアップロード", type="pdf")

if uploaded_pdf:
    y_guess, m_guess = p0.extract_year_month_from_text(uploaded_pdf.name)
    
    # 年月が両方揃っているかチェック
    info_complete = True if (y_guess and m_guess) else False
    
    final_year, final_month = y_guess, m_guess

    # どちらかが欠けている場合のみ、入力を求める画面を表示
    if not info_complete:
        st.subheader("❓ カレンダー情報の補完")
        st.warning("ファイル名から年・月を特定できませんでした。入力してください。")
        col_y, col_m = st.columns(2)
        with col_y:
            final_year = st.number_input("年 (西暦)", min_value=2024, max_value=2030, value=y_guess if y_guess else 2025)
        with col_m:
            final_month = st.number_input("月", min_value=1, max_value=12, value=m_guess if m_guess else 1)
    
    # カレンダー計算
    days_in_month = calendar.monthrange(final_year, final_month)[1]
    first_wd_idx = calendar.monthrange(final_year, final_month)[0]
    wd_names = ["月", "火", "水", "木", "金", "土", "日"]
    
    st.success(f"📌 {final_year}年{final_month}月として処理します。({days_in_month}日間 / 1日は{wd_names[first_wd_idx]}曜日)")

    # 解析実行ボタン
    # 情報が揃っている、または手入力が完了した状態で表示
    if drive_service:
        if st.button("解析を実行する", type="primary"):
            with st.spinner("解析中..."):
                time_master_dic = p0.time_schedule_from_drive(drive_service, SHEET_ID)
                pdf_res = p0.pdf_reader(uploaded_pdf, target_staff, days_in_month, time_master_dic)
                
                if isinstance(pdf_res, dict) and "error_type" in pdf_res:
                    st.error(f"❌ 解析失敗: {pdf_res.get('msg', '日程不一致などのエラー')}")
                else:
                    for wp_key, data in pdf_res.items():
                        my_shift, others, original_wp = data
                        st.success(f"✅ 全関門突破: {original_wp}")
                        st.divider()
                        st.header(f"📍 勤務地: {original_wp}")
                        st.write("👤 自分のシフト")
                        st.dataframe(my_shift)
                        st.write("🕒 時程表")
                        st.dataframe(time_master_dic[wp_key]["df"])
