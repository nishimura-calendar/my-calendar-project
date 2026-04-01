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
    st.set_page_config(page_title="Shift CSV Export", layout="wide")
    st.title("📅 勤務データ抽出・CSV出力システム")

    with st.sidebar:
        st.header("条件設定")
        target_staff = st.text_input("検索氏名", value="田坂 友愛")
        target_date = st.date_input("対象日")
        file_id = st.text_input("時程表スプレッドシートID", value="1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE")

    uploaded_pdf = st.file_uploader("勤務表PDFをアップロード", type="pdf")

    if uploaded_pdf and target_staff:
        if st.button("🚀 解析・CSV生成開始"):
            drive_service = get_gcp_services()
            if not drive_service: st.stop()
            
            with st.spinner("データを解析中..."):
                # 時程表（マスター）の取得
                time_dic = p0.download_and_extract_schedule(drive_service, file_id)
                # PDF（当日シフト）の解析
                pdf_stream = io.BytesIO(uploaded_pdf.read())
                pdf_dic = p0.pdf_reader(pdf_stream, target_staff)
                
                # 3つのCSVデータの生成
                shifts, holidays, events = p0.generate_all_csv_data(pdf_dic, time_dic, target_date)
                
                if shifts or holidays or events:
                    st.success("解析完了。以下のボタンから各CSVを取得してください。")
                    
                    c1, c2, c3 = st.columns(3)
                    
                    with c1:
                        st.markdown("### 📋 シフト")
                        if shifts:
                            df_s = pd.DataFrame(shifts)
                            st.dataframe(df_s, hide_index=True)
                            st.download_button("📥 シフト.csv を保存", df_s.to_csv(index=False, header=False).encode('utf-8-sig'), "シフト.csv", "text/csv")
                        else: st.info("該当なし")

                    with c2:
                        st.markdown("### 🏖️ 休日")
                        if holidays:
                            df_h = pd.DataFrame(holidays)
                            st.dataframe(df_h, hide_index=True)
                            st.download_button("📥 休日.csv を保存", df_h.to_csv(index=False, header=False).encode('utf-8-sig'), "休日.csv", "text/csv")
                        else: st.info("該当なし")

                    with c3:
                        st.markdown("### 🎫 イベント")
                        if events:
                            df_e = pd.DataFrame(events)
                            st.dataframe(df_e, hide_index=True)
                            st.download_button("📥 イベント.csv を保存", df_e.to_csv(index=False, header=False).encode('utf-8-sig'), "イベント.csv", "text/csv")
                        else: st.info("該当なし")
                else:
                    st.warning("解析結果が空です。氏名やファイルが正しいか確認してください。")

if __name__ == "__main__":
    main()
