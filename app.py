import streamlit as st
import practice_0 as p0
from googleapiclient.discovery import build
from google.oauth2 import service_account
import calendar

# 共有設定されているスプレッドシートID
SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="シフト・時程統合管理", layout="wide")
st.title("📅 シフト・時程 統合管理システム")

# 認証処理
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
    uploaded_pdf = st.file_uploader("PDFファイルをアップロード", type="pdf")
    if st.button("🛑 STOP", type="primary"):
        st.error("プログラムを停止しました。")
        st.stop()

# メインフロー
if uploaded_pdf:
    y, m = p0.extract_year_month_from_text(uploaded_pdf.name)
    
    # 年月が不明なら即停止（不確実な処理をさせない）
    if y is None or m is None:
        st.error("ファイル名から年・月を特定できません。以前の状態に戻すかプログラムを停止します。")
        st.stop()
    
    # 確定情報の提示
    days_in_month = calendar.monthrange(y, m)[1]
    st.info(f"📌 {y}年{m}月として解析の準備が完了しました。（{days_in_month}日間）")

    if st.button("2. 解析を実行する", type="primary"):
        if not drive_service:
            st.error("Google Driveへの接続権限がありません。以前の状態に戻すかプログラムを停止します。")
            st.stop()

        with st.spinner("スプレッドシートから時程表を取得中..."):
            try:
                time_master_dic = p0.time_schedule_from_drive(drive_service, SHEET_ID)
            except Exception as e:
                st.error(f"スプレッドシートの読み込みに失敗しました。以前の状態に戻すかプログラムを停止します。")
                st.stop()

        with st.spinner("PDFを解析中..."):
            try:
                pdf_res = p0.pdf_reader(uploaded_pdf, target_staff, days_in_month, time_master_dic)
                
                if pdf_res:
                    for wp_key, data in pdf_res.items():
                        my_shift, others, original_wp = data
                        st.success(f"✅ 解析完了: {original_wp}")
                        st.divider()
                        
                        col1, col2 = st.columns([1, 1])
                        with col1:
                            st.subheader("👤 自分のシフト")
                            st.dataframe(my_shift, use_container_width=True)
                        with col2:
                            st.subheader("🕒 対応する時程表")
                            st.dataframe(time_master_dic[wp_key]["df"], use_container_width=True)
                        
                        st.subheader("👥 他のスタッフ")
                        st.dataframe(others, use_container_width=True)
                else:
                    st.warning("条件に一致するデータが見つかりませんでした。以前の状態に戻すかプログラムを停止します。")
                    st.stop()
                    
            except Exception:
                st.error("解析中に予期せぬエラーが発生しました。以前の状態に戻すかプログラムを停止します。")
                st.stop()
else:
    st.write("サイドバーから解析したいPDFを選択してください。")
