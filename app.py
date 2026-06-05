import streamlit as st
import practice_0 as p0
import pandas as pd

def main():
    st.title("シフトカレンダー管理システム")
    
    # 1. 時程表辞書の初期化
    if 'time_dic' not in st.session_state:
        st.session_state.time_dic = {"T1": pd.DataFrame(), "T2": pd.DataFrame()}

    uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")
    
    if uploaded_file:
        # 2. 検証処理
        pdf_df, status, location = p0.load_and_validate_pdf(uploaded_file, 2026, 1, st.session_state.time_dic)
        
        if status == "通過":
            st.success(f"検証完了: 勤務地 {location}")
            
            # スタッフ選択
            staff_list = pdf_df.iloc[:, 0].dropna().unique().tolist()
            target_staff = st.selectbox("スタッフを選択", options=staff_list)
            
            if target_staff:
                extracted = p0.extract_target_data(pdf_df, target_staff, location)
                
                # 表示処理
                st.write("#### my_daily_shift")
                st.dataframe(extracted['my_daily_shift'])
                st.write("#### other_daily_shift")
                st.dataframe(extracted['other_daily_shift'].head(10))
        else:
            st.error(status)

if __name__ == "__main__":
    main()
