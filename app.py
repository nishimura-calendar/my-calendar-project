import streamlit as st
import pandas as pd

# 時刻変換関数（読み込み時に適用）
def format_time_value(val):
    try:
        f = float(val)
        h = int(f)
        m = int(round((f - h) * 60))
        return f"{h:02d}:{m:02d}"
    except (ValueError, TypeError):
        return str(val)

# データ読み込み（前回作成したロジックを統合）
def load_and_convert_time_schedule(csv_path):
    df = pd.read_csv(csv_path, header=0).fillna('')
    time_schedule_dict = {}
    locations = df.iloc[:, 0].unique()
    
    for loc in locations:
        if str(loc).strip():
            loc_df = df[df.iloc[:, 0] == loc].copy()
            # 数値列（3列目以降と仮定）を時刻変換
            for col in loc_df.columns[3:]:
                loc_df[col] = loc_df[col].apply(format_time_value)
            time_schedule_dict[str(loc).strip()] = loc_df
    return time_schedule_dict

def main():
    st.title("シフトカレンダー作成システム")
    
    csv_file = "シフトカレンダー.xlsx - time_schdule.csv"
    
    # 状態管理の初期化
    if 'data' not in st.session_state:
        st.session_state.data = None
    if 'selected_key' not in st.session_state:
        st.session_state.selected_key = None

    # スタートボタン
    if st.button("スタート"):
        st.session_state.data = load_and_convert_time_schedule(csv_file)
        st.rerun()

    # データが読み込まれていたらキーごとのボタンを表示
    if st.session_state.data:
        st.subheader("勤務地を選択してください")
        cols = st.columns(len(st.session_state.data))
        
        for i, key in enumerate(st.session_state.data.keys()):
            if cols[i].button(key):
                st.session_state.selected_key = key
        
        # 選択された勤務地の表示
        if st.session_state.selected_key:
            st.write(f"### 選択中: {st.session_state.selected_key}")
            st.dataframe(st.session_state.data[st.session_state.selected_key])

if __name__ == "__main__":
    main()
