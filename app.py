import streamlit as st
import practice_0 as p0
import pandas as pd

def main():
    st.title("シフトカレンダー管理システム")
    
    # 1. 時程表辞書の準備（デモ用ダミー）
    if 'time_dic' not in st.session_state:
        st.session_state.time_dic = {"T1": pd.DataFrame(), "T2": pd.DataFrame()}
        
    uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")
    
    if uploaded_file:
        # 2. PDF検証と勤務地抽出
        pdf_df, status, location = p0.load_and_validate_pdf(uploaded_file, 2026, 1, st.session_state.time_dic)
        
        if status == "通過":
            st.success(f"PDF検証完了: 勤務地 {location} を特定しました")
            
            # 3. [2]終了時のデータ表示
            st.write("### [2]終了時のデータ保持状態")
            
            # 抽出したデータの一部を表示
            st.write(f"#### 勤務地: {location}")
            
            st.write("#### 1. time_schedule (参照用)")
            st.write("格納済み") # 実際のデータフレームを表示可
            
            st.write("#### 2. my_daily_shift (抽出データ)")
            st.dataframe(pdf_df.head(3))
            
            st.write("#### 3. other_daily_shift (その他データ)")
            st.dataframe(pdf_df.tail(3))
            
        else:
            st.error(status)
            # ここにPDFプレビュー表示を組み込めます

if __name__ == "__main__":
    main()
