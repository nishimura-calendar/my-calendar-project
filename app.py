import streamlit as st
import practice_0 as p0
import pandas as pd

def main():
    st.title("シフトカレンダー管理システム")
    
    # 事前準備：時程表辞書の初期化
    if 'time_dic' not in st.session_state:
        # 実際にはここでスプレッドシートから読み込んだデータを格納します
        st.session_state.time_dic = {"T1": pd.DataFrame(), "T2": pd.DataFrame()}

    uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")
    
    if uploaded_file:
        # PDF検証処理
        pdf_df, status, location = p0.load_and_validate_pdf(uploaded_file, 2026, 1, st.session_state.time_dic)
        
        if status == "通過":
            st.success(f"検証完了: 勤務地 {location}")
            
            # スタッフ選択
            target_staff = st.selectbox("スタッフを選択してください", options=pdf_df.iloc[:, 0].dropna().unique())
            
            if target_staff:
                # 抽出実行
                extracted = p0.extract_target_data(pdf_df, target_staff, location)
                
                # データの表示
                st.write("### [2]終了時の保持データ")
                st.write("#### 1. my_daily_shift (個人シフト)")
                st.dataframe(extracted['my_daily_shift'])
                
                st.write("#### 2. other_daily_shift (他スタッフ)")
                st.dataframe(extracted['other_daily_shift'].head(10))
                
                st.write("#### 3. time_schedule (参照)")
                st.dataframe(st.session_state.time_dic.get(location, pd.DataFrame()))
        else:
            st.error(status)

if __name__ == "__main__":
    main()
