import streamlit as st
import practice_0 as p0
import pandas as pd

def main():
    st.title("シフトカレンダー管理システム")
    
    # 時程表（辞書型）
    if 'time_dic' not in st.session_state:
        st.session_state.time_dic = {"T1": pd.DataFrame(), "T2": pd.DataFrame()}

    uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")
    
    if uploaded_file:
        # PDF読み込みと検証
        pdf_df, status, location = p0.load_and_validate_pdf(uploaded_file, st.session_state.time_dic)
        
        if status == "通過":
            # 全スタッフリストを生成して表示
            staff_list = p0.get_staff_list(pdf_df)
            target_staff = st.selectbox("カレンダーを作成するスタッフを選択してください", options=staff_list)
            
            if target_staff:
                extracted = p0.extract_target_data(pdf_df, target_staff)
                
                # 結果表示
                st.write(f"### {target_staff} のシフト情報")
                st.dataframe(extracted['my_daily_shift'])
                
                st.write("#### 他スタッフ名簿（確認用）")
                st.dataframe(extracted['other_daily_shift'].head(5))
        else:
            st.error(status)

if __name__ == "__main__":
    main()
