import streamlit as st
from googleapiclient.discovery import build
from google.oauth2 import service_account
import practice_0 as p0

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="シフト・時程管理", layout="wide")
st.title("📅 シフト・時程 統合管理システム")

@st.cache_resource
def get_unified_services():
    if "gcp_service_account" in st.secrets:
        creds = service_account.Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=["https://www.googleapis.com/auth/drive.readonly", "https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        return build('drive', 'v3', credentials=creds), build('sheets', 'v4', credentials=creds)
    return None, None

drive_service, sheets_service = get_unified_services()

if sheets_service:
    try:
        # ここで呼び出し
        time_dic = p0.time_schedule_from_drive(sheets_service, SHEET_ID)
        st.sidebar.success("✅ 時程表 同期完了")
    except Exception as e:
        st.error(f"時程表の取得に失敗しました: {e}")
        st.stop()

    with st.sidebar:
        target_staff = st.text_input("名前", value="西村 文宏")
        uploaded_pdf = st.file_uploader("PDF", type="pdf")

    if target_staff and uploaded_pdf:
        if st.button("解析実行"):
            info = p0.extract_year_month_from_text(uploaded_pdf.name)
            if not info:
                st.error("ファイル名から年月が判別できません。")
                st.stop()
                
            pdf_res = p0.pdf_reader(uploaded_pdf, target_staff, info)
            
            if isinstance(pdf_res, dict) and "error" in pdf_res:
                st.error(pdf_res["error"])
                st.dataframe(pdf_res["df"]) # 第二関門失敗時のPDF内容表示
                st.stop()

            for wp_key, data in pdf_res.items():
                my_shift, others, wp_name = data
                st.header(f"📍 勤務地: {wp_name}")
                if wp_key in time_dic:
                    st.subheader("① 自分のシフト")
                    st.dataframe(my_shift)
                    st.subheader("② 他スタッフ")
                    st.dataframe(others)
                    st.subheader("🕒 時程表")
                    st.dataframe(time_dic[wp_key])
                else:
                    st.error(f"勤務地『{wp_name}』が時程表に見つかりません。")
