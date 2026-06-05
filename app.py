import streamlit as st
import pandas as pd
import practice_0 as p0

def main():
    st.title("シフトカレンダー管理システム")
    
    # [1] 時程表読み込み（画面表示なし）
    if 'time_dic' not in st.session_state:
        st.session_state.time_dic = p0.load_master_from_sheets()

    # [2] PDF（CSV）アップロード
    uploaded_file = st.file_uploader("シフトCSVをアップロード", type="csv")
    
    if uploaded_file:
        df = pd.read_csv(uploaded_file)
        
        # 勤務地の特定 (例: A列の2行目にT1がある前提)
        location = str(df.iloc[0, 0]).strip()
        
        # スタッフリスト作成（人名行のみ抽出）
        staff_list = df[df.iloc[:, 0].astype(str).str.contains('|'.join(['前田', '武輪', '水野', '米田', '奥村', '南川', '矢野', '岸田']))].iloc[:, 0].unique().tolist()
        
        target_staff = st.selectbox("カレンダー登録するスタッフを選んで下さい。", options=staff_list)
        
        if target_staff:
            # 抽出処理
            data = p0.register_shift_data(df, target_staff, location, st.session_state.time_dic)
            
            st.success(f"{target_staff} のデータを登録しました")
            
            with st.expander("データ詳細を確認"):
                st.write("#### my_daily_shift")
                st.dataframe(data["my_daily_shift"])
                st.write("#### other_daily_shift")
                st.dataframe(data["other_daily_shift"])
                st.write("#### time_schedule")
                st.dataframe(data["time_schedule"])

if __name__ == "__main__":
    main()
