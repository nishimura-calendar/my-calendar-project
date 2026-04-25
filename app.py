import streamlit as st
import pandas as pd
import gspread # スプレッドシート操作用
from practice_0 import rebuild_shift_table, get_master_data_from_gsheets

st.set_page_config(layout="wide")
st.title("📅 シフト・時程 統合管理システム")

# スプレッドシートIDの設定
SPREADSHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

# 1. マスターデータの読み込み
try:
    # ※認証設定（st.secrets等）が完了している前提
    # gc = gspread.service_account(...) 
    # sh = gc.open_by_key(SPREADSHEET_ID)
    # master_locations, time_schedules = get_master_data_from_gsheets(sh)
    
    # テスト用にCSVから読み込み（認証がない場合）
    jiteihyo_df = pd.read_csv("時程表.xlsx - Table 1.csv")
    master_locations = ["T1", "T2", "免税店"] # A列から取得する想定
except Exception as e:
    st.error(f"マスターデータの読み込みに失敗しました: {e}")
    st.stop()

# 設定
with st.sidebar:
    target_name = st.text_input("名前", value="四村")
    expected_days = st.number_input("日数", value=31)
    expected_weekday = st.selectbox("第1曜日", ["月", "火", "水", "木", "金", "土", "日"], index=3)

uploaded_file = st.file_uploader("PDFをアップロード", type="pdf")

if uploaded_file:
    with open("temp.pdf", "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    result, message = rebuild_shift_table(
        "temp.pdf", target_name, expected_days, expected_weekday, master_locations
    )

    if not result:
        # --- 不一致の場合：理由とPDFを表示 ---
        st.error(f"❌ 解析エラー: {message}")
        st.write("### PDFの生データ（読み取り内容）")
        st.dataframe(pd.read_csv("時程表.xlsx - Table 1.csv")) # 代替表示例
    else:
        # --- 一致した場合：3つの表を表示 ---
        st.success(f"✅ 検問通過（勤務地: {result['location']}）")
        
        # ① 時程表 (Time Schedule)
        st.subheader("① タイムスケジュール（時程表）")
        st.write(f"勤務地「{result['location']}」の定義を表示します。")
        # st.dataframe(time_schedules[result['location']])

        # ② あなたのシフト (My Daily Shift)
        st.subheader(f"② {target_name}さんの抽出シフト")
        st.table(pd.DataFrame([result['my_shift']], columns=[f"{i+1}日" for i in range(len(result['my_shift']))]))

        # ③ 他のスタッフのシフト (Other Staff Shift)
        st.subheader("③ 他スタッフのシフト（再構築データ）")
        st.dataframe(pd.DataFrame(result['others_shift']))
