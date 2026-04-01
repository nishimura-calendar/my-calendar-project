import streamlit as st
import practice_0 as p0
import io
import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build

def get_sheets_service():
    try:
        creds_info = st.secrets["gcp_service_account"]
        credentials = service_account.Credentials.from_service_account_info(
            creds_info,
            scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
        )
        return build('sheets', 'v4', credentials=credentials)
    except Exception as e:
        st.error(f"Google認証に失敗しました: {e}")
        return None

def main():
    st.set_page_config(page_title="勤務地紐付け確認", layout="wide")
    st.title("🔍 勤務地名・紐付け不一致の調査")

    target_staff = st.sidebar.text_input("検索する氏名", value="田坂 友愛")
    pdf_file = st.file_uploader("勤務表PDFをアップロード", type="pdf")
    spreadsheet_id = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

    if pdf_file and target_staff:
        if st.button("データ抽出を実行"):
            service = get_sheets_service()
            if not service: return
            
            # 1. スプレッドシートから勤務地リストを取得
            time_dic = p0.time_schedule_from_drive(service, spreadsheet_id)
            
            # 2. PDFから勤務地とシフトを取得
            pdf_stream = io.BytesIO(pdf_file.read())
            pdf_dic = p0.pdf_reader(pdf_stream, target_staff)

            # --- 確認用表示エリア ---
            st.header("1. 読み取られた勤務地名の比較")
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("📄 PDFから抽出")
                if pdf_dic:
                    for key, val in pdf_dic.items():
                        st.code(f"表示名: {val['raw_name']}\n(照合キー: {key})")
                else:
                    st.warning("氏名が見つからない、または勤務地を抽出できませんでした。")

            with col2:
                st.subheader("📊 スプレッドシートから抽出")
                if time_dic:
                    for key, val in time_dic.items():
                        st.code(f"表示名: {val['raw_name']}\n(照合キー: {key})")
                else:
                    st.warning("スプレッドシートからデータを取得できませんでした。")

            # 3. 紐付け結果の表示
            st.divider()
            st.header("2. 紐付け結果の確認")
            
            final_data = p0.data_integration(pdf_dic, time_dic)
            
            if final_data:
                for key, data in final_data.items():
                    raw_name = pdf_dic[key]["raw_name"]
                    st.success(f"✅ 紐付け成功: {raw_name}")
                    with st.expander("詳細データを見る"):
                        st.write("自分のシフト")
                        st.dataframe(data[0])
                        st.write("対応する時程表")
                        st.dataframe(data[2])
            else:
                st.error("❌ 紐付けに失敗しました。")
                st.info("上の「照合キー」を比較して、文字が微妙に違っていないか確認してください。")
                st.info("例：PDFは『T1』、シートは『T1(羽田)』などの違いがあると紐付けできません。")

if __name__ == "__main__":
    main()
