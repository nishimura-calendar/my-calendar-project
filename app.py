import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from practice_0 import rebuild_shift_table, get_master_data

# --- 設定：ご提示いただいた情報を反映 ---
SPREADSHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(layout="wide")
st.title("📅 シフト・時程 統合管理システム")

@st.cache_data
def load_master_from_gsheet():
    # 認証スコープの設定
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    # Streamlit Secretsに保存したサービスアカウント情報を使用
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], 
        scopes=scopes
    )
    client = gspread.authorize(creds)
    
    # IDで直接スプレッドシートを開く
    sh = client.open_by_key(SPREADSHEET_ID)
    worksheet = sh.get_worksheet(0) # 1番目のシートを選択
    data = worksheet.get_all_values()
    
    # 1行目をヘッダーとしてデータフレーム化
    return pd.DataFrame(data[1:], columns=data[0])

# --- 1. マスターデータの読み込み実行 ---
try:
    jiteihyo_df = load_master_from_gsheet()
    # 勤務地リストとスケジュール定義を抽出
    master_locations, time_schedules = get_master_data(jiteihyo_df)
    st.sidebar.success("✅ マスターデータを読み込みました")
except Exception as e:
    st.error(f"❌ マスター読み込み失敗: {e}")
    st.info("【確認】サービスアカウントにスプレッドシートの閲覧権限が付与されているか確認してください。")
    st.stop()

# --- 2. 解析・検問UI ---
with st.sidebar:
    st.header("検問基準")
    target_name = st.text_input("氏名", value="四村")
    expected_days = st.number_input("日数", value=30)
    expected_weekday = st.selectbox("第一曜日", ["月", "火", "水", "木", "金", "土", "日"], index=3)

uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")

if uploaded_file:
    # (解析処理と3つの表の表示ロジックは前の実装を継続)
    pass
