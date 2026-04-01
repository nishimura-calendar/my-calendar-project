import streamlit as st
import practice_0 as p0
import io
import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build

def get_gcp_services():
    """GCPサービス（Drive, Sheets）の構築"""
    try:
        creds_info = st.secrets["gcp_service_account"]
        credentials = service_account.Credentials.from_service_account_info(
            creds_info,
            scopes=[
                'https://www.googleapis.com/auth/spreadsheets.readonly',
                'https://www.googleapis.com/auth/drive.readonly'
            ]
        )
        drive_service = build('drive', '3', credentials=credentials)
        return drive_service
    except Exception as e:
        st.error(f"GCP認証エラー: {e}")
        return None

def main():
    st.set_page_config(page_title="シフト・時程 統合システム", layout="wide")
    
    st.title("📅 シフト・時程表 統合表示 (Drive Excel版)")
    st.info("ドライブ上の「時程表.xlsx」を自動取得し、アップロードされたPDFと紐付けます。")

    # サイドバー設定
    st.sidebar.header("設定")
    target_staff = st.sidebar.text_input("検索する氏名", value="田坂 友愛")
    # 基本事項に記載のID
    excel_file_id = st.sidebar.text_input("ExcelファイルID", value="1diDgaB--1vn5amCMmDGPv-Ld3IIIF-nK")
    
    pdf_file = st.file_uploader("勤務表PDFをアップロードしてください", type="pdf")

    if pdf_file and target_staff and excel_file_id:
        if st.button("解析と紐付けを実行"):
            drive_service = get_gcp_services()
            if not drive_service: return
            
            with st.spinner("データを取得・解析中..."):
                # 1. Google Driveから時程表Excelをダウンロード・解析
                time_dic = p0.download_and_extract_excel(drive_service, excel_file_id)
                
                # 2. PDF解析
                pdf_stream = io.BytesIO(pdf_file.read())
                pdf_dic = p0.pdf_reader(pdf_stream, target_staff)

                # 解析状況の表示
                st.subheader("🔍 解析状況の確認")
                c_pdf, c_xls = st.columns(2)
                with c_pdf:
                    st.write("**PDFの勤務地:**")
                    if pdf_dic:
                        for k in pdf_dic.keys(): st.success(f"✅ {k}")
                    else: st.error("氏名が見つかりません")
                with c_xls:
                    st.write("**Excel(Drive)の勤務地:**")
                    if time_dic:
                        for k in time_dic.keys(): st.success(f"✅ {k}")
                    else: st.error("Excelから勤務地が見つかりません。共有設定やIDを確認してください。")

                # 3. 紐付け処理
                final_data = p0.data_integration(pdf_dic, time_dic)
                
                if final_data:
                    for loc_key, content in final_data.items():
                        st.divider()
                        st.header(f"📍 拠点: {loc_key}")
                        
                        tab1, tab2 = st.tabs(["📋 あなたの予定", "⏱ 全体時程"])
                        with tab1:
                            st.subheader("本日のシフト")
                            st.dataframe(content[0], use_container_width=True)
                            st.subheader("同じ拠点のメンバー")
                            st.dataframe(content[1], use_container_width=True)
                        with tab2:
                            st.subheader("拠点のタイムスケジュール")
                            st.dataframe(content[2], use_container_width=True)
                else:
                    if pdf_dic and time_dic:
                        st.warning("勤務地名が一致しないため紐付けできませんでした。")

    else:
        st.info("サイドバーで条件を確認し、PDFをアップロードしてください。")

if __name__ == "__main__":
    main()
