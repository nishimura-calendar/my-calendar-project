import streamlit as st
import pandas as pd
from googleapiclient.discovery import build
from google.oauth2 import service_account
import practice_0 as p0

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="シフト・時程統合システム", layout="wide")
st.title("📅 シフト・時程 統合管理システム")

@st.cache_resource
def get_g_services():
    """ドライブ用とスプレッドシート用の2つのサービスを返す"""
    if "gcp_service_account" in st.secrets:
        info = st.secrets["gcp_service_account"]
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=[
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/spreadsheets.readonly"
            ]
        )
        # 両方のサービスを作成
        drive_service = build('drive', 'v3', credentials=creds)
        sheets_service = build('sheets', 'v4', credentials=creds)
        return drive_service, sheets_service
    return None, None

# --- 1. サービスの取得 ---
drive_service, sheets_service = get_g_services()

if sheets_service:
    try:
        # sheets_serviceを直接渡すように変更
        time_dic = p0.time_schedule_from_drive(sheets_service, SHEET_ID)
        st.sidebar.success("✅ スプレッドシート読み込み成功")
    except Exception as e:
        st.error(f"❌ スプレッドシート取得失敗: {e}")
        st.stop()
else:
    st.error("❌ 認証情報が見つかりません。")
    st.stop()

# --- 以降のコード（UIと解析実行）は前回提示したものと同じです ---
