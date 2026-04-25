import streamlit as st
import pandas as pd
from googleapiclient.discovery import build
from google.oauth2 import service_account
import practice_0 as p0

# --- 1. 定数・設定 ---
SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

def get_g_service():
    """
    Secretsから認証情報を読み込み、Google APIサービスを返す
    """
    try:
        # GitHub/Streamlit CloudのSecretsから取得
        if "gcp_service_account" in st.secrets:
            info = st.secrets["gcp_service_account"]
            creds = service_account.Credentials.from_service_account_info(
                info, scopes=["https://www.googleapis.com/auth/drive.readonly"]
            )
            return build('drive', 'v3', credentials=creds)
        else:
            return None
    except Exception as e:
        st.error(f"認証初期化エラー: {e}")
        return None

# --- 2. ページ初期化 ---
st.set_page_config(page_title="シフト解析・紐付け", layout="wide")
st.title("📅 シフト解析・紐付け確認画面")

# セッションにサービスを保持（再読み込み対策）
if 'g_service' not in st.session_state or st.session_state.g_service is None:
    st.session_state.g_service = get_g_service()

service = st.session_state.g_service

# --- 3. UI ---
with st.sidebar:
    st.header("解析設定")
    target_staff = st.text_input("解析する名前", value="西村 文宏")
    uploaded_pdf = st.file_uploader("PDFアップロード", type="pdf")
    
    if st.button("設定を再読み込み"):
        st.session_state.g_service = get_g_service()
        st.rerun()

# --- 4. メイン処理 ---
if target_staff and uploaded_pdf:
    if st.button("解析実行", type="primary"):
        # A. PDF解析
        pdf_results, year, month, consistency_report = p0.pdf_reader(
            uploaded_pdf, target_staff, uploaded_pdf.name
        )
        
        # B. 時程表取得
        time_dic = {}
        if service:
            try:
                time_dic = p0.time_schedule_from_drive(service, SHEET_ID)
            except Exception as e:
                st.error(f"スプレッドシート取得失敗: {e}")
                st.info("※サービスアカウントにスプレッドシートの閲覧権限があるか再確認してください。")
        else:
            st.error("Google Drive認証情報が見つかりません。Secretsの設定を確認してください。")

        # C. 報告と紐付け
        if consistency_report:
            for place, report in consistency_report.items():
                st.warning(f"⚠️ {place}: {report['reason']}")

        if pdf_results:
            st.success(f"🔍 {year}年{month}月 解析完了")
            
            for work_place, data in pdf_results.items():
                st.divider()
                st.header(f"📍 勤務地: {work_place}")
                
                # スプレッドシート側のキーと照合
                matched_time_sched = None
                norm_wp = p0.normalize_text(work_place)
                for t_key, t_df in time_dic.items():
                    if norm_wp == p0.normalize_text(t_key):
                        matched_time_sched = t_df
                        break
                
                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("🟢 my_daily_shift")
                    st.dataframe(data[0], use_container_width=True)
                with col2:
                    st.subheader("👥 other_daily_shift")
                    st.dataframe(data[1], use_container_width=True)
                
                st.subheader(f"🕒 time_schedule ({work_place})")
                if matched_time_sched is not None:
                    st.dataframe(matched_time_sched, use_container_width=True)
                else:
                    st.error("紐付け失敗: スプレッドシートのA列に該当する勤務地名がありません。")
                    if time_dic:
                        st.info(f"取得済み勤務地: {list(time_dic.keys())}")
        else:
            st.error("指定された名前のデータがPDF内に見つかりません。")
