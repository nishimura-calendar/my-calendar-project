import streamlit as st
import practice_0 as p0
from googleapiclient.discovery import build
from google.oauth2 import service_account

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="シフト・時程 統合管理", layout="wide")
st.title("📅 シフト・時程 統合管理システム")

@st.cache_resource
def get_unified_services():
    try:
        if "gcp_service_account" in st.secrets:
            creds = service_account.Credentials.from_service_account_info(
                st.secrets["gcp_service_account"],
                scopes=["https://www.googleapis.com/auth/drive.readonly", "https://www.googleapis.com/auth/spreadsheets.readonly"]
            )
            return build('drive', 'v3', credentials=creds), build('sheets', 'v4', credentials=creds)
    except Exception as e:
        st.error(f"❌ スプレッドシート取得失敗: {e}")
    return None, None

drive_service, sheets_service = get_unified_services()

if sheets_service:
    try:
        # 時程表（正）の読み込み
        time_dic = p0.time_schedule_from_drive(sheets_service, SHEET_ID)
    except Exception as e:
        st.error(f"❌ スプレッドシート取得失敗: {e}")
        st.stop()

    with st.sidebar:
        target_staff = st.text_input("解析する名前", value="西村 文宏")
        uploaded_pdf = st.file_uploader("PDFアップロード", type="pdf")

    if target_staff and uploaded_pdf:
        if st.button("解析実行"):
            # ファイル名から情報を抽出（正）
            y, m, exp_days, exp_wd = p0.extract_year_month_from_text(uploaded_pdf.name)
            
            # PDF解析とチェック
            pdf_res = p0.pdf_reader(uploaded_pdf, target_staff, exp_days, exp_wd)
            
            if "error" in pdf_res:
                st.error(f"関門突破失敗: {pdf_res['error']}")
                st.stop()

            # --- 第一関門 ＆ 第二関門 ＆ 第三関門の統合表示 ---
            for wp_key, data in pdf_res.items():
                my_shift, others, original_wp_name = data
                
                # 時程表との紐付け（勤務地をkeyにする）
                if wp_key in time_dic:
                    st.success(f"✅ 全関門突破: {original_wp_name}")
                    st.divider()
                    st.subheader(f"📍 勤務地: {original_wp_name}")
                    
                    st.write("🕒 **time_schedule (時程表)**")
                    st.dataframe(time_dic[wp_key])
                    
                    st.write("👤 **my_daily_shift (自分のシフト)**")
                    st.dataframe(my_shift)
                    
                    st.write("👥 **other_daily_shift (他スタッフ)**")
                    st.dataframe(others)
                else:
                    st.error(f"❌ 紐付け失敗: 勤務地『{original_wp_name}』が時程表に存在しません。")

else:
    st.warning("システムを稼働させるにはGoogle APIの認証が必要です。")
