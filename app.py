import streamlit as st
import practice_0 as p0
import pandas as pd

# 時程表を読み込むためのヘルパー（事前準備）
def get_time_schedule_dict():
    # 実際にはここでCSVやスプレッドシートから読み込みます
    # 例として空の辞書を返す
    return {}

def main():
    st.title("シフトカレンダー管理システム")
    
    # 1. データの準備
    if 'time_dic' not in st.session_state:
        st.session_state.time_dic = get_time_schedule_dict()
        
    uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")
    
    if uploaded_file:
        # 2. 検証処理
        pdf_df, status = p0.load_and_validate_pdf(uploaded_file, 2026, 1, st.session_state.time_dic)
        
        if status == "通過":
            st.success("PDFの検証が完了しました")
            
            # 3. [2]終了時の状態表示（全データ表示）
            st.write("### [2]終了時の保持データ")
            
            # time_schedule の表示
            st.write("#### 1. time_schedule")
            st.json(list(st.session_state.time_dic.keys())) # キーの確認
            
            # my_daily_shift の表示
            st.write("#### 2. my_daily_shift")
            st.dataframe(pdf_df.head(5))
            
            # other_daily_shift の表示
            st.write("#### 3. other_daily_shift")
            st.dataframe(pdf_df.tail(5))
            
        else:
            st.error(status)

if __name__ == "__main__":
    main()
