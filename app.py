import streamlit as st
import pandas as pd

def format_time_value(val):
    """数値を15分刻みの時刻形式 (HH:MM) に変換"""
    try:
        f = float(val)
        h = int(f)
        m = int(round((f - h) * 60))
        return f"{h:02d}:{m:02d}"
    except (ValueError, TypeError):
        return str(val)

def load_time_schedule_data(file_path):
    """
    時程表CSVを読み込み、勤務地ごとに辞書形式で格納し、
    内部の時間データを時刻形式へ変換済みにして保持する
    """
    df = pd.read_csv(file_path, header=0).fillna('')
    # 勤務地列(0列目)でグループ化して保持
    time_schedule_dict = {}
    
    # 全データを勤務地Keyごとに管理
    locations = df.iloc[:, 0].unique()
    for loc in locations:
        if loc:
            loc_df = df[df.iloc[:, 0] == loc].copy()
            # 数値列（時間データ）を時刻変換
            for col in loc_df.columns[3:]: # 4列目以降が時間データと想定
                loc_df[col] = loc_df[col].apply(format_time_value)
            time_schedule_dict[loc] = loc_df
            
    return time_schedule_dict

# --- Streamlit 表示用UI ---
def display_schedule_ui(time_schedule_dict):
    st.subheader("時程表の確認")
    
    # Key（勤務地）の選択
    selected_key = st.selectbox("確認したい勤務地を選択してください", list(time_schedule_dict.keys()))
    
    if selected_key:
        st.write(f"### 勤務地: {selected_key} の時程表")
        # 変換済みのデータフレームを表示
        st.dataframe(time_schedule_dict[selected_key])
