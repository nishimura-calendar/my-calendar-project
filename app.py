import streamlit as st
import pandas as pd
import numpy as np

# 1. 辞書作成用関数
@st.cache_data
def create_location_shift_dict(file_path):
    df = pd.read_excel(file_path)
    location_dict = {}
    current_location = None
    
    for _, row in df.iterrows():
        # A列に値がある場合、それを新しい勤務地キーとして登録
        if pd.notna(row.iloc[0]) and str(row.iloc[0]).strip() != "nan":
            current_location = str(row.iloc[0]).strip()
            location_dict[current_location] = []
        
        # 現在の勤務地グループにデータを追加
        if current_location:
            shift_info = {
                'シフトコード': row.iloc[1],
                'ロッカー': row.iloc[2],
                'time_data': {}
            }
            # D列(インデックス3)以降を走査し、数値のみを時間データとして抽出
            for i in range(3, len(row)):
                val = row.iloc[i]
                if isinstance(val, (int, float)) and not np.isnan(val):
                    shift_info['time_data'][df.columns[i]] = val
                elif isinstance(val, str): # 文字列が出たら終了
                    break
            location_dict[current_location].append(shift_info)
    return location_dict

# 2. UI構築
st.title("勤務地別時程表検索")

file_path = '時程表.xlsx' # 対象ファイル
try:
    shift_dict = create_location_shift_dict(file_path)
    
    # 勤務地選択
    locations = list(shift_dict.keys())
    selected_location = st.selectbox("勤務地を選択してください", locations)
    
    # ボタン押下で表示
    if st.button("時程を表示"):
        st.subheader(f"勤務地: {selected_location} の時程")
        
        # 該当するデータを表示
        data = shift_dict[selected_location]
        df_display = pd.DataFrame(data)
        
        # time_dataの中身を展開して見やすく表示
        st.dataframe(df_display)
        
except Exception as e:
    st.error(f"データの読み込み中にエラーが発生しました: {e}")
