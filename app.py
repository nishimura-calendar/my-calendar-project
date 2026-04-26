import streamlit as st
import pandas as pd
from googleapiclient.discovery import build
from google.oauth2 import service_account
import practice_0 as p0

# スプレッドシートID（時程表：正）
SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="シフト・時程 統合管理", layout="wide")
st.title("📅 シフト・時程 統合管理システム")

@st.cache_resource
def get_unified_services():
    """Google APIサービスの取得"""
    try:
        if "gcp_service_account" in st.secrets:
            creds = service_account.Credentials.from_service_account_info(
                st.secrets["gcp_service_account"],
                scopes=[
                    "https://www.googleapis.com/auth/drive.readonly",
                    "https://www.googleapis.com/auth/spreadsheets.readonly"
                ]
            )
            return build('drive', 'v3', credentials=creds), build('sheets', 'v4', credentials=creds)
    except Exception as e:
        st.error(f"❌ API接続失敗: {e}")
    return None, None

drive_service, sheets_service = get_unified_services()

# --- 事前準備: 時程表の読み込み ---
if sheets_service:
    try:
        # practice_0.pyのロジックで時程表（正）を辞書化
        time_dic = p0.time_schedule_from_drive(sheets_service, SHEET_ID)
        st.sidebar.success("✅ 時程表（マスター）同期完了")
    except Exception as e:
        st.error(f"❌ 時程表の取得に失敗しました: {e}")
        st.stop()
else:
    st.error("認証情報が設定されていません。")
    st.stop()

# --- ユーザー入力エリア ---
with st.sidebar:
    st.header("解析設定")
    target_staff = st.text_input("解析対象者氏名", value="西村 文宏")
    uploaded_pdf = st.file_uploader("シフト表PDFをアップロード", type="pdf")

if target_staff and uploaded_pdf:
    if st.button("解析実行", type="primary"):
        # 1. ファイル名から「年・月・期待される日数・第一曜日」を算出（ファイル名＝正）
        expected_info = p0.extract_year_month_from_text(uploaded_pdf.name)
        
        if not expected_info:
            st.error("❌ ファイル名から年月を特定できません。ファイル名に『2026年1月』等の形式を含めてください。")
            st.stop()

        # 2. PDF解析（第1・第2関門チェックを含む）
        # pdf_reader内で iloc[] を使った整合性チェックを行う
        pdf_results = p0.pdf_reader(uploaded_pdf, target_staff, expected_info)

        # --- 第2関門チェックの結果判定 ---
        if isinstance(pdf_results, dict) and "error" in pdf_results:
            st.error(pdf_results["error"])
            
            # 不一致の証拠としてPDFから読み取った生のDataFrameを表示
            if "df_for_display" in pdf_results:
                st.warning("⚠️ PDFから読み取られた実際の内容（座標確認用）:")
                st.dataframe(pdf_results["df_for_display"])
            
            st.info("💡 ファイル名とPDFの中身が一致しているか確認してください。")
            st.stop() # ここで処理を終了

        # --- 第3関門: 紐付けと表示 ---
        if pdf_results:
            st.success(f"✅ 全関門を通過しました（{expected_info['year']}年{expected_info['month']}月）")
            
            for wp_norm_key, data in pdf_results.items():
                my_shift, others, original_wp_name = data
                
                st.divider()
                st.header(f"📍 勤務地: {original_wp_name}")
                
                # 時程表（正）との紐付け確認
                if wp_norm_key in time_dic:
                    # 成功した場合の表示
                    col1, col2 = st.columns(2)
                    with col1:
                        st.subheader("👤 自分のシフト (my_daily_shift)")
                        st.dataframe(my_shift, use_container_width=True)
                    with col2:
                        st.subheader("👥 他スタッフ (other_daily_shift)")
                        st.dataframe(others, use_container_width=True)
                    
                    st.subheader("🕒 適用される時程表 (time_schedule)")
                    st.dataframe(time_dic[wp_norm_key], use_container_width=True)
                else:
                    # 第一関門（勤務地名の一致）に失敗した場合
                    st.error(f"❌ 紐付け失敗: 勤務地『{original_wp_name}』が時程表マスターに登録されていません。")
        else:
            st.warning(f"指定された氏名『{target_staff}』がPDF内に見つかりませんでした。")
