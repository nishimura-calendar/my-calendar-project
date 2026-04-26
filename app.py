import streamlit as st
from googleapiclient.discovery import build
from google.oauth2 import service_account
import practice_0 as p0
import pandas as pd

# 時程表のスプレッドシートID
SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="シフト・時程管理", layout="wide")
st.title("📅 シフト抽出・時程管理システム")

@st.cache_resource
def get_unified_services():
    """GCPサービスアカウントの認証とサービス構築"""
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

drive_service, sheets_service = get_unified_services()

if sheets_service:
    # 1. スプレッドシート（時程表）からマスターデータを読み込み
    time_dic = p0.time_schedule_from_drive(sheets_service, SHEET_ID)
    
    with st.sidebar:
        st.header("🔍 設定・確認")
        target_staff = st.text_input("抽出対象氏名", value="西村 文宏")
        uploaded_pdf = st.file_uploader("PDFを選択（ファイル名に年月を含めてください）", type="pdf")
        
        st.divider()
        # --- ここからデバッグ表示: スプレッドシートのKey（勤務地）を表示 ---
        st.subheader("📋 取得済み勤務地(Key)")
        if time_dic:
            # 読み込めているKeyを一覧表示
            keys_list = list(time_dic.keys())
            st.info(f"現在 {len(keys_list)} 個の勤務地を認識しています。")
            for k in keys_list:
                st.code(k)
        else:
            st.error("スプレッドシートからデータが取得できていません。IDや権限を確認してください。")
        # --- ここまでデバッグ表示 ---

    # 2. メイン処理
    if target_staff and uploaded_pdf:
        if st.button("解析実行", type="primary"):
            # ファイル名から年月・日数を特定
            info = p0.extract_year_month_from_text(uploaded_pdf.name)
            
            if not info:
                st.error("ファイル名から年月を特定できません。例：『2026年2月シフト.pdf』")
                st.stop()
            
            # PDFの解析と抽出実行
            pdf_res = p0.pdf_reader(uploaded_pdf, target_staff, info, time_dic)
            
            if pdf_res:
                for wp_key, data in pdf_res.items():
                    st.divider()
                    st.header(f"📍 勤務地: {data['wp_name']}")
                    
                    # 抽出されたデータの表示
                    col1, col2 = st.columns(2)
                    with col1:
                        st.subheader("👤 自分のシフト")
                        st.dataframe(data['my_shift'], use_container_width=True)
                    
                    with col2:
                        st.subheader("👥 他スタッフ（参考）")
                        st.dataframe(data['others'], use_container_width=True)
                        
                    # 座標情報の確認（必要に応じて表示）
                    with st.expander("詳細な座標情報を見る"):
                        st.json(data['drawing'])
            else:
                st.warning("データが見つかりませんでした。サイドバーの『取得済み勤務地(Key)』がPDF内の文字（T2など）と一致しているか確認してください。")
else:
    st.error("Secretsの設定（gcp_service_account）が見つかりません。")
