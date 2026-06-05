import streamlit as st
import pandas as pd
import practice_0 as p0

def main():
    st.title("シフトカレンダー管理システム")
    
    # [1] マスタの読み込み（裏側で処理、表示なし）
    if 'time_dic' not in st.session_state:
        st.session_state.time_dic = p0.load_master_from_sheets()

    # [2] CSVシフト表アップロード
    uploaded_file = st.file_uploader("シフトCSVをアップロード", type="csv")
    
    if uploaded_file:
        df = pd.read_csv(uploaded_file)
        
        # 勤務地の特定（A列の0行目がT1等の勤務地コードと仮定）
        location = str(df.iloc[0, 0]).strip()
        
        # スタッフリスト作成（人名行のみ抽出）
        def is_staff(val):
            v = str(val).strip()
            return v and not v.isdigit() and v not in ['T1', 'T2', 'シフトコード', 'nan']
            
        raw_list = df.iloc[:, 0].dropna().astype(str).unique()
        staff_list = [s for s in raw_list if is_staff(s)]
        
        target_staff = st.selectbox("カレンダー登録するスタッフを選んで下さい。", options=staff_list)
        
        if target_staff:
            # 抽出処理実行
            data = p0.register_shift_data(df, target_staff, location, st.session_state.time_dic)
            
            st.success(f"{target_staff} のデータを登録しました")
            
            # 結果表示（必要に応じて確認用として展開）
            with st.expander("データ詳細を確認"):
                st.write("#### 1. my_daily_shift (選択スタッフの2行)")
                st.dataframe(data["my_daily_shift"])
                st.write("#### 2. other_daily_shift (人名行のみ)")
                st.dataframe(data["other_daily_shift"])
                st.write("#### 3. time_schedule (マスタと照合)")
                st.dataframe(data["time_schedule"])

if __name__ == "__main__":
    main()
