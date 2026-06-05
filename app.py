import streamlit as st
import practice_0 as p0

def main():
    st.title("シフトカレンダー管理システム")
    
    # [1] 時程表の裏側読み込み
    if 'time_dic' not in st.session_state:
        st.session_state.time_dic = p0.load_master_from_sheets()

    # [2] PDFアップロード
    uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")
    
    if uploaded_file:
        # 関数呼び出しを引数に合わせて修正
        pdf_df, status, location = p0.load_and_validate_pdf(uploaded_file, st.session_state.time_dic)
        
        if status == "通過":
            # スタッフリスト作成
            staff_list = ["該当者なし"] + pdf_df.iloc[:, 0].dropna().astype(str).str.strip().unique().tolist()
            
            target_staff = st.selectbox("カレンダー登録するスタッフを選んで下さい。", options=staff_list)
            
            if target_staff:
                # データ抽出と登録
                st.session_state.registered_data = p0.register_shift_data(
                    pdf_df, target_staff, location, st.session_state.time_dic
                )
                
                st.success(f"{target_staff} のデータを登録しました")
                
                # 確認用表示
                with st.expander("データ詳細を確認"):
                    st.write("#### my_daily_shift (2行セット)")
                    st.dataframe(st.session_state.registered_data["my_daily_shift"])
                    
                    st.write("#### other_daily_shift (人名行のみ)")
                    st.dataframe(st.session_state.registered_data["other_daily_shift"])
                    
                    st.write("#### time_schedule")
                    st.dataframe(st.session_state.registered_data["time_schedule"])
        else:
            st.error(status)

if __name__ == "__main__":
    main()
