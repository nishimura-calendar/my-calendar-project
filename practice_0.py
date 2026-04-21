import streamlit as st
import shutil
import io
import pandas as pd
import practice_0 as p0
from googleapiclient.discovery import build
from google.oauth2 import service_account

def main():
    st.set_page_config(page_title="免税店シフト解析システム", layout="wide")
    st.title("🛡️ 免税店シフト解析 (デバッグ表示付)")

    # サイドバー：基本設定
    with st.sidebar:
        st.header("⚙️ 設定")
        target_name = st.text_input("解析する名前", value="西村 文宏")
        ss_id = st.text_input("時程表スプレッドシートID", value="1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE")
        show_debug = st.checkbox("【デバッグ】解析途中の表を表示する", value=True)
        
        if "gcp_service_account" in st.secrets:
            try:
                creds = service_account.Credentials.from_service_account_info(
                    st.secrets["gcp_service_account"],
                    scopes=['https://www.googleapis.com/auth/spreadsheets.readonly', 'https://www.googleapis.com/auth/drive.readonly']
                )
                service = build('drive', 'v3', credentials=creds)
            except Exception as e:
                st.error(f"Google認証に失敗しました: {e}")
                service = None
        else:
            st.warning("SecretsにGoogle認証情報が設定されていません。")
            service = None

    uploaded_file = st.file_uploader("シフト表（PDF）を選択してください", type="pdf")

    if uploaded_file and target_name:
        pdf_stream = io.BytesIO(uploaded_file.read())
        
        try:
            # 1. PDF解析
            with st.spinner("PDFを解析中..."):
                pdf_results, year, month = p0.pdf_reader(pdf_stream, target_name, uploaded_file.name)
            
            # 2. 時程表取得
            time_sched_dic = {}
            if service:
                with st.spinner("時程表を取得中..."):
                    time_sched_dic = p0.time_schedule_from_drive(service, ss_id)

            if pdf_results:
                st.success(f"✅ 解析完了: {year}年{month}月度")

                # --- デバッグ表示セクション ---
                if show_debug:
                    with st.expander("🔍 解析データの中身を確認する", expanded=True):
                        for place, data in pdf_results.items():
                            st.write(f"### 勤務地: {place}")
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                st.write("📅 **my_daily_shift (あなたの抽出シフト)**")
                                st.dataframe(data[0]) # data[0] = my_daily
                            
                            with col2:
                                st.write("👥 **other_daily_shift (他スタッフのデータ)**")
                                st.dataframe(data[1]) # data[1] = others
                            
                            st.write("⏱️ **time_schedule (対応する時程表)**")
                            if place in time_sched_dic:
                                st.dataframe(time_sched_dic[place])
                            else:
                                st.warning(f"時程表の中に '{place}' というキーが見つかりません。")
                
                # 3. データの紐付け
                integrated_dic = p0.integrate_with_warning(pdf_results, time_sched_dic)
                
                if integrated_dic:
                    # 4. カレンダーCSV生成
                    with st.spinner("カレンダーデータを生成中..."):
                        final_calendar_rows = p0.process_full_month(integrated_dic, year, month)
                    
                    df_csv = pd.DataFrame(final_calendar_rows[1:], columns=final_calendar_rows[0])
                    
                    st.subheader("📅 生成されたスケジュール（最終出力）")
                    st.dataframe(df_csv, use_container_width=True)
                    
                    csv_buffer = io.StringIO()
                    df_csv.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
                    
                    st.download_button(
                        label="📥 Googleカレンダー用CSVをダウンロード",
                        data=csv_buffer.getvalue(),
                        file_name=f"shift_{year}_{month}_{target_name}.csv",
                        mime="text/csv",
                    )
            else:
                st.error(f"'{target_name}' 様のデータが見つかりませんでした。")
                
        except Exception as e:
            st.error(f"処理中にエラーが発生しました: {e}")
            st.exception(e)

if __name__ == "__main__":
    main()
