import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from practice_0 import rebuild_shift_table, get_master_data

# スプレッドシートID
SPREADSHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(layout="wide")
st.title("📅 シフト・時程 統合管理システム")

# 1. マスターデータの自動読み込み
try:
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    client = gspread.authorize(creds)
    sh = client.open_by_key(SPREADSHEET_ID)
    master_locations, time_schedules = get_master_data(sh)
except Exception as e:
    st.error(f"マスター読み込み失敗: {e}")
    st.stop()

# 2. 検問パラメーター設定
with st.sidebar:
    st.header("検問基準設定")
    target_name = st.text_input("名前", value="四村")
    expected_days = st.number_input("日数", value=30)
    expected_weekday = st.selectbox("第一曜日", ["月", "火", "水", "木", "金", "土", "日"], index=3)

uploaded_file = st.file_uploader("PDFをアップロード", type="pdf")

if uploaded_file:
    with open("temp.pdf", "wb") as f: f.write(uploaded_file.getbuffer())
    
    # 3. 実行と検問
    result, message = rebuild_shift_table(
        "temp.pdf", target_name, expected_days, expected_weekday, master_locations
    )

    if not result:
        # --- 検問不合格時：理由と生データを表示 ---
        st.error(f"❌ 検問不合格: {message}")
        st.write("### 読み取り生データ（座標確認用）")
        import camelot
        st.dataframe(camelot.read_pdf("temp.pdf", flavor='stream')[0].df)
    else:
        # --- 検問合格時：3つの表を紐付け表示 ---
        st.success(f"✅ 全検問通過: {result['location']}のデータを抽出しました")
        
        col1, col2 = st.columns([1, 1])
        with col1:
            st.subheader("① 紐付け：時程表 (Time Schedule)")
            st.dataframe(time_schedules[result['location']])
        
        st.subheader(f"② {target_name}さんのシフト")
        st.table(pd.DataFrame([result['my_shift']], columns=[f"{i+1}日" for i in range(len(result['my_shift']))]))

        st.subheader("③ 他スタッフのシフト（座標一致）")
        st.dataframe(pd.DataFrame(result['others']))
