import streamlit as st
from googleapiclient.discovery import build
from google.oauth2 import service_account
import practice_0 as p0

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
    try:
        time_dic = p0.time_schedule_from_drive(sheets_service, SHEET_ID)
        st.sidebar.success("✅ 時程表 同期完了")
    except Exception as e:
        st.error(f"時程表の取得に失敗しました: {e}")
        st.stop()

    with st.sidebar:
        target_staff = st.text_input("氏名", value="西村 文宏")
        uploaded_pdf = st.file_uploader("PDFアップロード", type="pdf")

    if target_staff and uploaded_pdf:
        if st.button("解析実行", type="primary"):
            info = p0.extract_year_month_from_text(uploaded_pdf.name)
            if not info:
                st.error("ファイル名から年月を特定できません。")
                st.stop()
                
            pdf_res = p0.pdf_reader(uploaded_pdf, target_staff, info, time_dic)
            
            if isinstance(pdf_res, dict) and "error" in pdf_res:
                st.error(pdf_res["error"])
                st.warning("解析されたPDFの生データ（座標確認用）:")
                st.dataframe(pdf_res["df"])
                st.stop()

            if pdf_res:
                for wp_key, data in pdf_res.items():
                    st.divider()
                    st.header(f"📍 勤務地: {data['wp_name']}")
                    
                    # 指定座標の表示
                    draw = data['drawing']
                    st.caption(f"📏 設定座標: 中線X={draw['x']} / 中線Y={draw['y']} / 底罫線={draw['bottom']}")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.subheader("① 自分のシフト")
                        st.dataframe(data['my_shift'])
                    with col2:
                        st.subheader("② 他スタッフ")
                        st.dataframe(data['others'])
                    
                    st.subheader("🕒 対応する時程表")
                    st.dataframe(time_dic[wp_key]["df"])
            else:
                st.warning("該当するデータが見つかりませんでした。")
else:
    st.error("認証情報が見つかりません。")
