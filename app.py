import streamlit as st
import pandas as pd
import os

# 時刻変換関数
def format_time_value(val):
    try:
        f = float(val)
        h = int(f)
        m = int(round((f - h) * 60))
        return f"{h:02d}:{m:02d}"
    except (ValueError, TypeError):
        return str(val)

# データ読み込み処理
def load_and_convert_time_schedule(csv_path):
    # CSVファイルを読み込み
    df = pd.read_csv(csv_path, header=0).fillna('')
    time_schedule_dict = {}
    
    # 勤務地（A列）ごとのユニークリストを取得
    locations = df.iloc[:, 0].unique()
    
    for loc in locations:
        loc_str = str(loc).strip()
        if loc_str:
            # 該当勤務地のデータ抽出
            loc_df = df[df.iloc[:, 0] == loc].copy()
            # 4列目以降（時間データ）を時刻変換
            for col in loc_df.columns[3:]:
                loc_df[col] = loc_df[col].apply(format_time_value)
            time_schedule_dict[loc_str] = loc_df
    return time_schedule_dict

def main():
    st.title("シフトカレンダー作成システム")
    
    # ファイルパスの指定
    csv_file = "time_schedule.csv"
    
    # セッション管理
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
            st.error(f"ファイル {csv_file} が見つかりません。")

    # データ読み込み後、勤務地ボタンを表示
    if st.session_state.data:
        st.subheader("確認したい勤務地を選択してください")
        
        # 横並びボタンの生成
        keys = list(st.session_state.data.keys())
        cols = st.columns(len(keys))
        
        for i, key in enumerate(keys):
            if cols[i].button(key):
                st.session_state.selected_key = key
        
        # 選択された勤務地のテーブル表示
        if st.session_state.selected_key:
            st.write(f"### 勤務地: {st.session_state.selected_key} の時程表")
            st.dataframe(st.session_state.data[st.session_state.selected_key])

if __name__ == "__main__":
    main()
