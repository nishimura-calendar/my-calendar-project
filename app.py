import streamlit as st
import pandas as pd
import io
import re
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

try:
    from practice_0 import pdf_reader, extract_year_month, time_schedule_from_drive, data_integration
except Exception as e:
    st.error(f"❌ ファイル読み込みエラー: {e}"); st.stop()

# 設定
TIME_TABLE_ID = "1p7EBN1zTTt09etuQkZTIXBlNutUZqQkG"
SHIFT_PDF_FOLDER_ID = "1X9ThkHI4xPeUYa29FW3AmLll9gRz6EFd"
TARGET_STAFF = "西村文宏"

st.set_page_config(page_title="シフト管理システム", layout="wide")
st.title("📅 シフトカレンダー一括登録")

def get_gapi_service(service_name, version):
    from google.oauth2 import service_account
    info = dict(st.secrets["gcp_service_account"])
    # スコープをリストとして定義
    scopes = [
        'https://www.googleapis.com/auth/calendar',
        'https://www.googleapis.com/auth/drive.readonly'
    ]
    # 引数を正しく渡すように修正
    creds = service_account.Credentials.from_service_account_info(info, scopes=scopes)
    return build(service_name, version, credentials=creds)

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """時間割を解析し、連続する同じ担当区分を結合する"""
    # 終日イベントを追加
    final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", key])
    
    # 自分のシフトコード(12等)を取得
    shift_code = str(my_daily_shift.iloc[1, col]).strip()
    sched_clean = time_schedule.fillna("").astype(str)
    my_time_shift = sched_clean[sched_clean.iloc[:, 1] == shift_code]
    
    if not my_time_shift.empty:
        prev_label = None
        for t_col in range(2, time_
