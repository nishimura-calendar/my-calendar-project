import streamlit as st
import practice_0 as p0
import io
import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build

def get_gcp_services():
    try:
        creds_info = st.secrets["gcp_service_account"]
        credentials = service_account.Credentials.from_service_account_info(
            creds_info, 
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        return build('drive', 'v3', credentials=credentials)
    except Exception as e:
        st.error(f"GCP認証エラー: {e}")
        return None

def main():
    st.set_page_config(page_title="Shift Integration", layout="wide")
    st.title("📅 シフト・時程表 CSV出力")

    with st.sidebar:
        st.header("設定")
        target_staff = st.text_input("検索する氏名", value="田坂 友愛")
        target_date = st.date_input("対象の日付")
        file_id = st.text_input("時程表スプレッドシートID", value="1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE")

    uploaded_pdf = st.file_uploader("勤務表PDFをアップロードしてください", type="pdf")

    if uploaded_pdf and target_staff:
        if st.button("🚀 実行してCSVを生成"):
            drive_service = get_gcp_services()
            if not drive_service: st.stop()
            
            with st.spinner("データを解析しています..."):
                # 1. 時程表取得
                time_dic = p0.download_and_extract_schedule(drive_service, file_id)
                # 2. PDF解析
                pdf_stream = io.BytesIO(uploaded_pdf.read())
                pdf_dic = p0.pdf_reader(pdf_stream, target_staff)
                # 3. データ統合・CSV生成
                shifts, holidays, events = p0.generate_all_csv_data(pdf_dic, time_dic, target_date)
                
                if shifts or holidays or events:
                    st.success("解析が完了しました。")
                    
                    cols = st.columns(3)
                    
                    with cols[0]:
                        st.subheader("シフト.csv")
                        if shifts:
                            df_s = pd.DataFrame(shifts)
                            st.dataframe(df_s, hide_index=True)
                            csv_s = df_s.to_csv(index=False, header=False).encode('utf-8-sig')
                            st.download_button("📥 ダウンロード", csv_s, "シフト.csv", "text/csv")
                        else: st.info("データなし")

                    with cols[1]:
                        st.subheader("休日.csv")
                        if holidays:
                            df_h = pd.DataFrame(holidays)
                            st.dataframe(df_h, hide_index=True)
                            csv_h = df_h.to_csv(index=False, header=False).encode('utf-8-sig')
                            st.download_button("📥 ダウンロード", csv_h, "休日.csv", "text/csv")
                        else: st.info("データなし")

                    with cols[2]:
                        st.subheader("イベント.csv")
                        if events:
                            df_e = pd.DataFrame(events)
                            st.dataframe(df_e, hide_index=True)
                            csv_e = df_e.to_csv(index=False, header=False).encode('utf-8-sig')
                            st.download_button("📥 ダウンロード", csv_e, "イベント.csv", "text/csv")
                        else: st.info("データなし")
                else:
                    st.warning("該当するデータが見つかりませんでした。条件を確認してください。")

if __name__ == "__main__":
    main()
