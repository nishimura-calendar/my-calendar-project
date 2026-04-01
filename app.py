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
    st.set_page_config(page_title="Shift Integration System", layout="wide")
    st.title("📅 シフト・時程表 CSV出力システム")

    st.sidebar.header("ユーザー設定")
    target_staff = st.sidebar.text_input("検索氏名", value="田坂 友愛")
    target_date = st.sidebar.date_input("対象日")
    file_id = st.sidebar.text_input("時程表SS ID", value="1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE")
    
    uploaded_pdf = st.file_uploader("勤務表PDFをアップロード", type="pdf")

    if uploaded_pdf and target_staff:
        if st.button("🚀 解析・CSV生成"):
            drive_service = get_gcp_services()
            if not drive_service: st.stop()
            
            with st.spinner("解析中..."):
                time_dic = p0.download_and_extract_schedule(drive_service, file_id)
                pdf_stream = io.BytesIO(uploaded_pdf.read())
                pdf_dic = p0.pdf_reader(pdf_stream, target_staff)
                
                # CSVデータの生成
                shifts, holidays, events = p0.generate_calendar_data(pdf_dic, time_dic, target_date)
                
                if shifts or holidays or events:
                    st.success("解析完了。以下のボタンからCSVをダウンロードしてください。")
                    
                    c1, c2, c3 = st.columns(3)
                    
                    with c1:
                        if shifts:
                            df_s = pd.DataFrame(shifts)
                            csv_s = df_s.to_csv(index=False, header=False).encode('utf-8-sig')
                            st.download_button("📥 シフト.csv", csv_s, "シフト.csv", "text/csv")
                            st.dataframe(df_s)
                    
                    with c2:
                        if holidays:
                            df_h = pd.DataFrame(holidays)
                            csv_h = df_h.to_csv(index=False, header=False).encode('utf-8-sig')
                            st.download_button("📥 休日.csv", csv_h, "休日.csv", "text/csv")
                            st.dataframe(df_h)
                        else:
                            st.write("休日データなし")
                            
                    with c3:
                        if events:
                            df_e = pd.DataFrame(events)
                            csv_e = df_e.to_csv(index=False, header=False).encode('utf-8-sig')
                            st.download_button("📥 イベント.csv", csv_e, "イベント.csv", "text/csv")
                            st.dataframe(df_e)
                        else:
                            st.write("イベントデータなし")
                else:
                    st.error("紐付け可能なデータがありませんでした。")

if __name__ == "__main__":
    main()
