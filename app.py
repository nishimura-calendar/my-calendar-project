import streamlit as st
import practice_0 as p0
import io
import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build

def get_sheets_service():
    """Secretsから認証情報を読み込み、Google Sheets APIサービスを作成"""
    try:
        creds_info = st.secrets["gcp_service_account"]
        credentials = service_account.Credentials.from_service_account_info(
            creds_info,
            scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
        )
        return build('sheets', 'v4', credentials=credentials)
    except Exception as e:
        st.error(f"Google認証に失敗しました。Secretsの設定を確認してください。")
        return None

def main():
    st.set_page_config(page_title="シフト・時程 統合管理", layout="wide")
    
    st.title("📅 シフト・時程表 統合表示")
    st.markdown("ドライブ上のスプレッドシート(時程表)とPDF(勤務表)を紐付けます。")

    # サイドバー：ユーザーが変更する項目
    st.sidebar.header("設定")
    target_staff = st.sidebar.text_input("検索する氏名", value="田坂 友愛")
    spreadsheet_id = st.sidebar.text_input("スプレッドシートID", value="1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE")
    
    # ファイルアップロード
    pdf_file = st.file_uploader("勤務表PDFをアップロードしてください", type="pdf")

    if pdf_file and target_staff:
        if st.button("解析を開始する"):
            service = get_sheets_service()
            if not service: return
            
            with st.spinner("データを取得・解析中..."):
                # 1. スプレッドシートから情報を探す
                time_dic = p0.time_schedule_from_drive(service, spreadsheet_id)
                
                # 2. PDFから情報を探す
                pdf_stream = io.BytesIO(pdf_file.read())
                pdf_dic = p0.pdf_reader(pdf_stream, target_staff)

                # --- 実行結果の確認用エリア ---
                st.subheader("🔍 解析状況の確認")
                col_a, col_b = st.columns(2)
                with col_a:
                    st.write("**PDFから見つかった勤務地:**")
                    if pdf_dic:
                        for k in pdf_dic.keys(): st.success(f"✅ {k}")
                    else:
                        st.error("❌ 氏名が見つかりません")
                
                with col_b:
                    st.write("**シートから見つかった勤務地:**")
                    if time_dic:
                        for k in time_dic.keys(): st.success(f"✅ {k}")
                    else:
                        st.error("❌ 勤務地(T1,T2等)が見つかりません")

                # 3. 紐付けと表示
                final_data = p0.data_integration(pdf_dic, time_dic)
                
                if final_data:
                    st.divider()
                    for loc_key, content in final_data.items():
                        st.header(f"📍 拠点: {loc_key}")
                        
                        # 統合表示
                        tab1, tab2 = st.tabs(["📋 あなたの予定", "⏱ 全体時程"])
                        with tab1:
                            st.subheader("今日のシフト")
                            st.dataframe(content[0], use_container_width=True)
                            
                            st.subheader("同じ拠点の同僚")
                            st.dataframe(content[1], use_container_width=True)
                        
                        with tab2:
                            st.subheader("拠点のタイムスケジュール")
                            st.dataframe(content[2], use_container_width=True)
                else:
                    if pdf_dic and time_dic:
                        st.warning("勤務地名が一致しないため紐付けできませんでした。")
                        st.info("PDF側とシート側で名前（T1など）が同じか確認してください。")

    else:
        st.info("サイドバーで名前を確認し、PDFをアップロードしてください。")

if __name__ == "__main__":
    main()
