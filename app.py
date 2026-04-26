import streamlit as st
import practice_0 as p0
from googleapiclient.discovery import build
from google.oauth2 import service_account

# スプレッドシートID
SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="シフト・時程 統合管理", layout="wide")
st.title("📅 シフト・時程 統合管理システム")

@st.cache_resource
def get_unified_services():
    try:
        if "gcp_service_account" in st.secrets:
            info = st.secrets["gcp_service_account"]
            creds = service_account.Credentials.from_service_account_info(
                info,
                scopes=["https://www.googleapis.com/auth/drive.readonly", "https://www.googleapis.com/auth/spreadsheets.readonly"]
            )
            return build('drive', 'v3', credentials=creds), build('sheets', 'v4', credentials=creds)
    except Exception as e:
        st.error(f"❌ 認証エラー: {e}")
    return None, None

drive_service, sheets_service = get_unified_services()

with st.sidebar:
    st.header("解析設定")
    target_staff = st.text_input("解析する名前", value="西村 文宏")
    uploaded_pdf = st.file_uploader("PDFアップロード", type="pdf")

if sheets_service:
    try:
        # 第1関門（正）：時程表（マスター）の読み込み
        time_master_dic = p0.time_schedule_from_drive(sheets_service, SHEET_ID)
        st.sidebar.success("✅ 時程表（マスター）読み込み完了")
    except Exception as e:
        st.error(f"❌ スプレッドシート取得失敗: {e}")
        st.stop()
else:
    st.error("❌ Googleサービスに接続できません。")
    st.stop()

if target_staff and uploaded_pdf:
    if st.button("解析実行", type="primary"):
        # ファイル名（正）：基準情報を算出
        y, m, exp_days, exp_wd = p0.extract_year_month_from_text(uploaded_pdf.name)
        
        # PDF解析と関門チェック
        pdf_res = p0.pdf_reader(uploaded_pdf, target_staff, exp_days, time_master_dic)
        
        # 関門失敗時の処理
        if isinstance(pdf_res, dict) and "error_type" in pdf_res:
            if pdf_res["error_type"] == "WP_MISSING":
                st.error(f"❌ 第1関門突破失敗：PDFから読み取った見出しの一部に、マスター登録済みの勤務地名が見つかりません。")
                st.warning(f"PDFの見出し内容: {pdf_res['wp']}")
                st.info(f"登録済みの勤務地名: {', '.join([v['original_name'] for v in time_master_dic.values()])}")
            elif pdf_res["error_type"] == "DAY_MISMATCH":
                st.error(f"❌ 第2関門突破失敗：日程不一致。ファイル名基準:{pdf_res['exp']}日分に対し、PDF内容は{pdf_res['act']}日分あります。")
            elif pdf_res["error_type"] == "SYSTEM":
                st.error(f"❌ エラー: {pdf_res['msg']}")
            st.stop()

        # 第3関門：紐付け成功時の表示
        if pdf_res:
            for wp_key, data in pdf_res.items():
                my_shift, others, original_wp = data
                st.success(f"✅ 全関門突破: {original_wp}")
                st.divider()
                st.header(f"📍 勤務地: {original_wp}")
                
                col1, col2 = st.columns([1, 1])
                with
