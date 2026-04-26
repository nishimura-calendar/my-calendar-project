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
    """DriveとSheetsのサービスを統合的に取得"""
    if "gcp_service_account" in st.secrets:
        creds = service_account.Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=[
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/spreadsheets.readonly"
            ]
        )
        return build('drive', 'v3', credentials=creds), build('sheets', 'v4', credentials=creds)
    return None, None

# --- 1. データの準備 ---
drive_service, sheets_service = get_unified_services()

if sheets_service:
    try:
        # consideration_0.pyのロジックで読み込み
        time_dic = p0.time_schedule_from_drive(sheets_service, SHEET_ID)
        st.sidebar.success("✅ 時程表読み込み完了")
    except Exception as e:
        st.error(f"❌ スプレッドシート取得失敗: {e}")
        st.stop()
else:
    st.error("❌ 認証情報が見つかりません。")
    st.stop()

# --- 2. ユーザー操作パネル ---
with st.sidebar:
    st.header("解析設定")
    target_staff = st.text_input("解析する名前", value="西村 文宏")
    uploaded_pdf = st.file_uploader("PDFアップロード", type="pdf")

# --- 3. 解析結果の表示 ---
if target_staff and uploaded_pdf:
    if st.button("解析実行", type="primary"):
        # ファイル名から年月を抽出
        year, month = p0.extract_year_month_from_text(uploaded_pdf.name)
        
        # 打ち合わせ通りのPDF解析実行
        pdf_results = p0.pdf_reader(uploaded_pdf, target_staff)

        if pdf_results:
            st.success(f"🔍 {year}年{month}月 解析完了")
            
            for work_place, data in pdf_results.items():
                st.divider()
                # 打ち合わせ通り：勤務地を大きく表示
                st.header(f"📍 勤務地: {work_place}")
                
                # レイアウト：左に自分のシフト、右に他スタッフ
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    st.subheader("① 自分のシフト (日付・曜日を含む)")
                    st.dataframe(data[0], use_container_width=True) # 自分の2行
                    
                with col2:
                    st.subheader("② 他スタッフの稼働状況")
                    st.dataframe(data[1], use_container_width=True) # 自分以外の行
                
                # スプレッドシートから最適な時程表を紐付け
                st.subheader(f"🕒 時程定義の確認 ({work_place})")
                norm_wp = p0.normalize_text(work_place)
                matched_time = None
                for t_key, t_df in time_dic.items():
                    if norm_wp == p0.normalize_text(t_key):
                        matched_time = t_df
                        break
                
                if matched_time is not None:
                    # 勤務地ごとに異なる列構造をそのまま表示
                    st.dataframe(matched_time, use_container_width=True)
                else:
                    st.warning(f"スプレッドシート内に『{work_place}』の定義が見つかりません。")
        else:
            st.error(f"PDF内に『{target_staff}』さんのデータが見つかりません。")
