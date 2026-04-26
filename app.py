import streamlit as st
import pandas as pd
from googleapiclient.discovery import build  # これが重要です
from google.oauth2 import service_account
import practice_0 as p0

# 通信成功が確認されたスプレッドシートID
SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="シフト・時程統合システム", layout="wide")
st.title("📅 シフト・時程 統合管理システム")

@st.cache_resource
def get_g_service():
    """隠しフォルダ（.streamlit/secrets.toml）から鍵を読み込んで接続"""
    if "gcp_service_account" in st.secrets:
        info = st.secrets["gcp_service_account"]
        # 権限(drive.readonly)を使用
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )
        return build('drive', 'v3', credentials=creds)
    return None

# --- 1. スプレッドシート読み込み ---
service = get_g_service()
if service:
    try:
        # スプレッドシートから時程表を取得
        time_dic = p0.time_schedule_from_drive(service, SHEET_ID)
        st.sidebar.success("✅ スプレッドシート読み込み成功")
    except Exception as e:
        st.error(f"❌ スプレッドシート取得失敗: {e}")
        st.stop()
else:
    st.error("❌ 認証情報(secrets.toml)が見つかりません。")
    st.stop()

# --- 2. UI（設定） ---
with st.sidebar:
    st.header("解析設定")
    target_staff = st.text_input("解析する名前", value="西村 文宏")
    uploaded_pdf = st.file_uploader("PDFアップロード", type="pdf")

# --- 3. 解析実行 ---
if target_staff and uploaded_pdf:
    if st.button("解析実行", type="primary"):
        year, month = p0.extract_year_month_from_text(uploaded_pdf.name)
        pdf_results = p0.pdf_reader(uploaded_pdf, target_staff)

        if pdf_results:
            st.success(f"🔍 {year}年{month}月 解析完了")
            for work_place, data in pdf_results.items():
                st.divider()
                st.header(f"📍 勤務地: {work_place}")
                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("① 自分のシフト")
                    st.dataframe(data[0])
                with col2:
                    st.subheader("② 他スタッフ")
                    st.dataframe(data[1])
                
                st.subheader(f"🕒 時程表 ({work_place})")
                norm_wp = p0.normalize_text(work_place)
                matched_time = None
                for t_key, t_df in time_dic.items():
                    if norm_wp == p0.normalize_text(t_key):
                        matched_time = t_df
                        break
                if matched_time is not None:
                    st.dataframe(matched_time, use_container_width=True)
        else:
            st.error(f"PDF内に『{target_staff}』さんのデータが見つかりません。")
