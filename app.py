import streamlit as st
import practice_0 as p0

def main():
    st.title("シフトカレンダー管理システム")
    
    # [1] 時程表の裏側読み込み（表示なし）
    if 'time_dic' not in st.session_state:
        st.session_state.time_dic = p0.load_master_from_sheets()

    # [2] シフト表(PDF/CSV)アップロード
    uploaded_file = st.file_uploader("シフトファイルをアップロード", type=["csv", "pdf"])
    
    if uploaded_file and st.session_state.time_dic:
        # ここでファイルを読み込み、スタッフ選択へ進む
        # (解析ロジックは前の指示に基づき進行)
        st.write("時程表の読み込み完了。スタッフ選択へ進みます。")
        # ...以降のロジック...

if __name__ == "__main__":
    main()
