import streamlit as st
import pandas as pd
import os

# 1. 時刻変換関数
def format_time_value(val):
    try:
        f = float(val)
        h = int(f)
        m = int(round((f - h) * 60))
        return f"{h:02d}:{m:02d}"
    except (ValueError, TypeError):
        return str(val)

# 2. 時程表読み込み処理
def load_and_convert_time_schedule(csv_path):
    df = pd.read_csv(csv_path, header=0).fillna('')
    time_schedule_dict = {}
    
    # 勤務地（A列）ごとのデータを辞書に格納
    locations = df.iloc[:, 0].unique()
    for loc in locations:
        loc_str = str(loc).strip()
        if loc_str:
            loc_df = df[df.iloc[:, 0] == loc].copy()
            # 4列目以降（時間データ）を時刻変換
            for col in loc_df.columns[3:]:
                loc_df[col] = loc_df[col].apply(format_time_value)
            time_schedule_dict[loc_str] = loc_df
    return time_schedule_dict

# 3. メインアプリ
def main():
    st.title("シフトカレンダー作成システム")
    csv_file = "時程表" # GitHub上の名前に合わせる

    if 'data' not in st.session_state:
        st.session_state.data = None
    if 'selected_key' not in st.session_state:
        st.session_state.selected_key = None

    # スタートボタン
    if st.button("スタート"):
        if os.path.exists(csv_file):
            st.session_state.data = load_and_convert_time_schedule(csv_file)
            st.rerun()
        else:
            st.error(f"エラー: {csv_file} が見つかりません。GitHubに正しくアップロード・リネームされているか確認してください。")

    # 読み込み後の勤務地選択UI
    if st.session_state.data:
        st.subheader("確認したい勤務地を選択してください")
        keys = list(st.session_state.data.keys())
        cols = st.columns(len(keys))
        
        for i, key in enumerate(keys):
            if cols[i].button(key):
                st.session_state.selected_key = key
        
        if st.session_state.selected_key:
            st.write(f"### 勤務地: {st.session_state.selected_key}")
            st.dataframe(st.session_state.data[st.session_state.selected_key])

if __name__ == "__main__":
    main()
