import streamlit as st
import pandas as pd
import practice_0 as p0

st.set_page_config(layout="wide")

def main():
    st.title("デバッグ用：シフト管理システム")
    
    # [1] マスタ読み込みのデバッグ
    st.write("ステップ1: マスタ読み込み開始...")
    if 'time_dic' not in st.session_state:
        try:
            st.session_state.time_dic = p0.load_master_from_sheets()
            st.write("マスタ読み込み完了！")
        except Exception as e:
            st.error(f"マスタ読み込みエラー: {e}")
            return
    else:
        st.write("マスタは既に読み込まれています。")

    # [2] ファイルアップロード
    uploaded_file = st.file_uploader("シフトデータをアップロード", type=["csv"])
    
    if uploaded_file:
        st.write("ステップ2: ファイルアップロード確認")
        df = pd.read_csv(uploaded_file)
        st.write(f"ファイル読み込み成功！行数: {len(df)}")
        
        # スタッフリストの確認
        st.write("ステップ3: スタッフ抽出開始...")
        def is_staff(val):
            v = str(val).strip()
            return v and not v.isdigit() and v not in ['T1', 'T2', 'シフトコード', 'nan']
        
        staff_list = [s for s in df.iloc[:, 0].unique() if is_staff(s)]
        st.write(f"抽出されたスタッフ数: {len(staff_list)}")
        
        target_staff = st.selectbox("スタッフを選択してください", options=staff_list)
        
        if target_staff:
            data = p0.register_shift_data(df, target_staff, str(df.iloc[0, 0]).strip(), st.session_state.time_dic)
            st.success("抽出成功！")
            st.dataframe(data["my_daily_shift"])

if __name__ == "__main__":
    main()
