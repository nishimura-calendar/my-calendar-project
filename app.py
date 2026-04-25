import streamlit as st
import pandas as pd
import camelot
from practice_0 import rebuild_shift_table, get_master_data

st.set_page_config(layout="wide")
st.title("📅 シフト・時程 統合管理システム")

# スプレッドシート（Excel）の読み込み
try:
    # 実際のファイル名に合わせて指定
    jiteihyo_df = pd.read_excel("時程表 (30).xlsx") 
    master_locations, time_schedules = get_master_data(jiteihyo_df)
except Exception as e:
    st.error(f"マスターデータの読み込み失敗: {e}")
    st.stop()

# サイドバー設定
with st.sidebar:
    st.header("検問パラメーター")
    target_name = st.text_input("氏名", value="四村")
    expected_days = st.number_input("日数", value=30)
    expected_weekday = st.selectbox("第1曜日", ["月", "火", "水", "木", "金", "土", "日"], index=3)

uploaded_file = st.file_uploader("PDFをアップロード", type="pdf")

if uploaded_file:
    with open("temp.pdf", "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    # 解析実行
    result, message = rebuild_shift_table(
        "temp.pdf", target_name, expected_days, expected_weekday, master_locations
    )

    if not result:
        # --- ② 検問不一致時の表示 ---
        st.error(f"❌ 解析停止: {message}")
        st.info("理由を確認し、設定またはPDFファイルを見直してください。")
        st.write("### PDF読み取り生データ（座標確認用）")
        tables = camelot.read_pdf("temp.pdf", flavor='stream')
        if tables: st.dataframe(tables[0].df)
    else:
        # --- ③ 一致時の紐付け表示 ---
        st.success(f"✅ 検問合格（勤務地: {result['location']}）")
        
        # 3つの表を表示
        st.subheader("① 紐付け：時程表 (Time Schedule)")
        st.dataframe(time_schedules[result['location']])

        st.subheader(f"② {target_name}さんのシフト (My Daily Shift)")
        my_df = pd.DataFrame([result['my_shift']], columns=[f"{i+1}日" for i in range(len(result['my_shift']))])
        st.table(my_df)

        st.subheader("③ 他スタッフのシフト (Other Staff Shift)")
        others_df = pd.DataFrame(result['others_shift'], columns=[f"{i+1}日" for i in range(len(result['my_shift']))])
        st.dataframe(others_df)
