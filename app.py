import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
import practice_0 as p0

# 打ち合わせ通りのスプレッドシートID
SPREADSHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(layout="wide", page_title="完全版：シフト・時程統合システム")
st.title("📅 シフト・時程 統合管理システム")

# 1. Google Sheetsからの読込（Secrets使用）
@st.cache_data
def load_master():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    client = gspread.authorize(creds)
    sh = client.open_by_key(SPREADSHEET_ID)
    return p0.get_master_data(sh)

try:
    master_locations, time_dic = load_master()
    st.sidebar.success("✅ スプレッドシート読み込み完了")
except Exception as e:
    st.error(f"❌ マスター読み込み失敗: {e}")
    st.stop()

# 2. 検問パラメーター（サイドバー）
with st.sidebar:
    st.header("検問基準設定")
    target_name = st.text_input("氏名", value="四村")
    expected_days = st.number_input("期待する日数", value=30, step=1)
    expected_weekday = st.selectbox("第一曜日", ["月", "火", "水", "木", "金", "土", "日"], index=3)

uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")

if uploaded_file:
    with open("temp.pdf", "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    # 3. 解析と厳格な検問
    result, message = p0.rebuild_shift_table(
        "temp.pdf", target_name, expected_days, expected_weekday, master_locations
    )

    if not result:
        # 検問に落ちた場合、今までの苦労（生データ）を表示して原因を特定
        st.error(f"❌ 検問不合格：{message}")
        st.info("PDFの座標がズレているか、ファイルが間違っている可能性があります。")
        import camelot
        st.write("### PDF解析座標（生データ）")
        st.dataframe(camelot.read_pdf("temp.pdf", flavor='stream')[0].df)
    else:
        # 検問合格時：3つの表を100%の精度で表示
        st.success(f"✅ 検問合格：{result['location']}（{expected_days}日間）")
        
        st.divider()
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("① my_daily_shift")
            st.table(pd.DataFrame([result['my_shift']], columns=[f"{i+1}日" for i in range(len(result['my_shift']))]))
        
        with col2:
            st.subheader("② other_daily_shift")
            st.dataframe(pd.DataFrame(result['others']))

        st.subheader(f"③ time_schedule（{result['location']}定義）")
        matched_sched = time_dic.get(p0.normalize_text(result['location']))
        if matched_sched is not None:
            st.dataframe(matched_sched, use_container_width=True)
        else:
            st.error("紐付け失敗：スプレッドシート側の名称を確認してください。")
