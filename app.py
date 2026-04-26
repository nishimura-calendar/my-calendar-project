import streamlit as st
from googleapiclient.discovery import build
from google.oauth2 import service_account
import practice_0 as p0
import pandas as pd

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="シフト・時程 統合管理", layout="wide")
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
    time_dic = p0.time_schedule_from_drive(sheets_service, SHEET_ID)
    with st.sidebar:
        target_staff = st.text_input("抽出対象氏名", value="西村 文宏")
        uploaded_pdf = st.file_uploader("PDFを選択", type="pdf")

    if target_staff and uploaded_pdf:
        if st.button("解析実行", type="primary"):
            info = p0.extract_year_month_from_text(uploaded_pdf.name)
            if not info: st.error("ファイル名から年月を特定できません。"); st.stop()
            
            pdf_res = p0.pdf_reader(uploaded_pdf, target_staff, info, time_dic)
            
            if isinstance(pdf_res, dict) and "error" in pdf_res:
                st.error(pdf_res["error"]); st.dataframe(pdf_res["df"]); st.stop()

            if pdf_res:
                for wp_key, data in pdf_res.items():
                    st.divider()
                    st.header(f"📍 勤務地: {data['wp_name']}")
                    st.info(f"📏 座標情報: 中線X={data['drawing']['x']} / 中線Y={data['drawing']['y']} / 底罫線={data['drawing']['bottom']}")
                    
                    st.subheader("📅 列の区分（日付・曜日）")
                    st.dataframe(pd.DataFrame([data['header_date'], data['header_week']]), use_container_width=True)

                    c1, c2 = st.columns(2)
                    with c1: st.subheader("① 自分のシフト"); st.dataframe(data['my_shift'], use_container_width=True)
                    with c2: st.subheader("② 他スタッフ"); st.dataframe(data['others'], use_container_width=True)
                    
                    if wp_key in time_dic:
                        st.subheader("🕒 時程表")
                        st.dataframe(time_dic[wp_key]["df"], use_container_width=True)
            else:
                st.warning("データが見つかりませんでした。")
else:
    st.error("API設定（secrets）を確認してください。")
