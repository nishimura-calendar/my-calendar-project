import streamlit as st
import pandas as pd  # ここが不足していると pd が使えません
import practice_0 as p0

def main():
    st.title("シフトカレンダー管理システム")
    
    # 1. セッション状態の初期化（既に存在する場合は初期化しない）
    if 'time_dic' not in st.session_state:
        st.session_state.time_dic = {"T1": pd.DataFrame()} 
        
    uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")
    
    if uploaded_file:
        # 2. PDF読み込みと検証
        pdf_df, status, location = p0.load_and_validate_pdf(uploaded_file, st.session_state.time_dic)
        
        if status == "通過":
            # 3. スタッフリストの取得
            staff_list = p0.get_staff_list(pdf_df)
            
            # 4. ユーザー選択
            target_staff = st.selectbox("カレンダー登録するスタッフを選んで下さい。", options=staff_list)
            
            if target_staff:
                # 5. 辞書登録（セッション保持）
                # ユーザー選択後にデータを辞書形式で抽出・登録
                st.session_state.registered_data = p0.register_shift_data(pdf_df, target_staff, location, st.session_state.time_dic)
                
                # 6. 確認用表示
                st.success(f"{target_staff} のデータを登録しました")
                
                with st.expander("データ詳細を確認"):
                    st.write("#### my_daily_shift")
                    st.dataframe(st.session_state.registered_data["my_daily_shift"])
                    
                    st.write("#### other_daily_shift")
                    st.dataframe(st.session_state.registered_data["other_daily_shift"].head(5))
                    
                    st.write("#### time_schedule")
                    st.dataframe(st.session_state.registered_data["time_schedule"])
        else:
            st.error(status)

if __name__ == "__main__":
    main()
