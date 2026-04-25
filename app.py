import streamlit as st
import pandas as pd
from googleapiclient.discovery import build
from google.oauth2 import service_account
import practice_0 as p0
import io

# 打ち合わせ通りのスプレッドシートID
SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="完全版：シフト・時程管理システム", layout="wide")
st.title("📅 シフト・時程 統合管理システム")

@st.cache_resource
def get_sheets_service():
    """Secretsから認証情報を取得し、確実に読み込めるサービスを構築"""
    if "gcp_service_account" in st.secrets:
        info = st.secrets["gcp_service_account"]
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        return build('sheets', 'v4', credentials=creds)
    return None

def load_spreadsheet_data(service, sheet_id):
    """Google API経由でスプレッドシートの内容をDataFrame化"""
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range="A:ZZ"
    ).execute()
    values = result.get('values', [])
    if not values: return pd.DataFrame()
    return pd.DataFrame(values[1:], columns=values[0])

# --- 1. マスター読み込み ---
service = get_sheets_service()
if service:
    try:
        master_df = load_spreadsheet_data(service, SHEET_ID)
        master_locations, time_dic = p0.get_master_data_from_df(master_df)
        st.sidebar.success("✅ スプレッドシート読み込み成功")
    except Exception as e:
        st.error(f"❌ スプレッドシート取得エラー: {e}")
        st.stop()
else:
    st.error("❌ 認証情報が見つかりません。")
    st.stop()

# --- 2. 検問パラメーター設定 ---
with st.sidebar:
    st.header("検問基準")
    target_name = st.text_input("氏名", value="四村")
    expected_days = st.number_input("日数", value=30)
    expected_weekday = st.selectbox("第一曜日", ["月", "火", "水", "木", "金", "土", "日"], index=3)

uploaded_file = st.file_uploader("PDFをアップロード", type="pdf")

if uploaded_file:
    with open("temp.pdf", "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    # 3. 解析と厳格な検問の実行
    result, message = p0.rebuild_shift_table(
        "temp.pdf", target_name, expected_days, expected_weekday, master_locations
    )

    if not result:
        st.error(f"❌ 検問不合格：{message}")
        st.info("ファイル名と内容が一致しているか、もう一度確認してください。")
    else:
        st.success(f"✅ 検問合格：{result['location']}")
        
        # 4. 3つの表の紐付け表示
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("① my_daily_shift")
            st.table(pd.DataFrame([result['my_shift']], columns=[f"{i+1}日" for i in range(len(result['my_shift']))]))
        with col2:
            st.subheader("② other_daily_shift")
            st.dataframe(pd.DataFrame(result['others']))

        st.subheader(f"③ time_schedule ({result['location']})")
        matched_sched = time_dic.get(p0.normalize_text(result['location']))
        if matched_sched is not None:
            st.dataframe(matched_sched, use_container_width=True)
        else:
            st.error("時程表の紐付けに失敗しました。")
