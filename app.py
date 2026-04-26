import streamlit as st
import practice_0 as p0
from googleapiclient.discovery import build
from google.oauth2 import service_account
import calendar

# 共通定数
SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="シフト解析", layout="wide")
st.title("📅 シフト・時程 統合管理システム")

# サービスアカウント認証
@st.cache_resource
def get_drive_service():
    try:
        if "gcp_service_account" in st.secrets:
            info = st.secrets["gcp_service_account"]
            creds = service_account.Credentials.from_service_account_info(
                info, scopes=["https://www.googleapis.com/auth/drive.readonly"]
            )
            return build('drive', 'v3', credentials=creds)
    except Exception:
        return None
    return None

drive_service = get_drive_service()

# サイドバー
with st.sidebar:
    st.header("1. 入力設定")
    target_staff = st.text_input("スタッフ名", value="西村 文宏")
    uploaded_pdf = st.file_uploader("PDFアップロード", type="pdf")
    if st.button("🛑 STOP", type="primary"):
        st.error("プログラムを停止しました。")
        st.stop()

# メイン処理
if uploaded_pdf:
    # ファイル名解析
    y, m = p0.extract_year_month_from_text(uploaded_pdf.name)
    
    # 年月が不明なら停止
    if y is None or m is None:
        st.error("ファイル名から年・月を特定できません。以前の状態に戻すかプログラムを停止します。")
        st.stop()
    
    # 確定情報の表示
    days_in_month = calendar.monthrange(y, m)[1]
    st.info(f"📌 {y}年{m}月として解析の準備が整いました。")

    if st.button("2. 解析を実行する", type="primary"):
        if not drive_service:
            st.error("認証に失敗しています。以前の状態に戻すかプログラムを停止します。")
            st.stop()

        with st.spinner("スプレッドシートと照合中..."):
            try:
                # 時程表取得
                time_master_dic = p0.time_schedule_from_drive(drive_service, SHEET_ID)
                
                # PDF解析
                pdf_res = p0.pdf_reader(uploaded_pdf, target_staff, days_in_month, time_master_dic)
                
                if pdf_res:
                    for wp_key, data in pdf_res.items():
                        my_shift, others, original_wp = data
                        st.success(f"✅ 解析完了: {original_wp}")
                        st.divider()
                        st.subheader(f"📍 勤務地: {original_wp}")
                        st.write("👤 自分のシフト")
                        st.dataframe(my_shift)
                        st.write("🕒 時程表")
                        st.dataframe(time_master_dic[wp_key]["df"])
                else:
                    st.warning("データが見つかりませんでした。以前の状態に戻すかプログラムを停止します。")
                    st.stop()
                    
            except Exception as e:
                st.error(f"実行時エラーが発生しました。以前の状態に戻すかプログラムを停止します。")
                # 必要に応じてエラーの詳細をログに残す
                st.stop()
