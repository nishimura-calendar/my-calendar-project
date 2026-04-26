import streamlit as st
from googleapiclient.discovery import build
from google.oauth2 import service_account
import practice_0 as p0
import pandas as pd

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="シフト管理システム", layout="wide")

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
        uploaded_pdf = st.file_uploader("PDFを選択（ファイル名に年月を含めてください）", type="pdf")

    if target_staff and uploaded_pdf:
        if st.button("解析実行", type="primary"):
            # ファイル名から情報を抽出
            info = p0.extract_year_month_from_text(uploaded_pdf.name)
            if not info:
                st.error("ファイル名に『2026年1月』のような形式が含まれていません。")
                st.stop()
            
            pdf_res = p0.pdf_reader(uploaded_pdf, target_staff, info, time_dic)
            
            if pdf_res:
                for wp_key, data in pdf_res.items():
                    st.header(f"📍 勤務地: {data['wp_name']}")
                    st.write(f"📏 座標: X={data['drawing']['x']}, Y=10, Bottom=20")
                    
                    st.subheader("📅 列の区分")
                    st.dataframe(pd.DataFrame([data['header_date'], data['header_week']]))

                    col1, col2 = st.columns(2)
                    with col1:
                        st.subheader("① 自分のシフト")
                        st.dataframe(data['my_shift'])
                    with col2:
                        st.subheader("② 他のスタッフ")
                        st.dataframe(data['others'])
            else:
                st.warning("データが見つかりませんでした。ファイル名とPDF内の日付・曜日が一致しているか確認してください。")
