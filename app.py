import streamlit as st
import pandas as pd
from googleapiclient.discovery import build
from google.oauth2 import service_account
import practice_0 as p0

# スプレッドシートID
SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="シフト・時程統合管理", layout="wide")
st.title("📅 シフト・時程 統合管理システム")

@st.cache_resource
def get_unified_services():
    """DriveとSheetsの両方のサービスを構築"""
    if "gcp_service_account" in st.secrets:
        creds = service_account.Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=[
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/spreadsheets.readonly"
            ]
        )
        drive_service = build('drive', 'v3', credentials=creds)
        sheets_service = build('sheets', 'v4', credentials=creds)
        return drive_service, sheets_service
    return None, None

# --- 1. 認証とスプレッドシート読み込み ---
drive_service, sheets_service = get_unified_services()

if sheets_service:
    try:
        # consideration_0.pyの構造に基づきマスターデータを取得
        time_dic = p0.time_schedule_from_drive(sheets_service, SHEET_ID)
        st.sidebar.success("✅ 時程表（マスター）読み込み完了")
    except Exception as e:
