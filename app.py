import streamlit as st
import pandas as pd
import io
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# 1. 小数から時刻表記(H:MM)への変換関数
def format_time(val):
    try:
        f_val = float(val)
        h = int(f_val)
        m = int(round((f_val - h) * 60))
        return f"{h}:{m:02d}"
    except (ValueError, TypeError):
        return val

# 2. データを整形する関数
def process_data(df):
    location_data = {}
    # A列が空でない行（勤務地行）のインデックス
    location_indices = df[df.iloc[:, 0].notna()].index.tolist()
    
    for i, start_idx in enumerate(location_indices):
        key = str(df.iloc[start_idx, 0])
        
        # 範囲確定：次の勤務地行の手前まで
        end_idx = location_indices[i+1] if i+1 < len(location_indices) else df.index[-1] + 1
        schedule = df.iloc[start_idx:end_idx].copy()
        
        # --- 列方向の処理 ---
        # 勤務地行のD列(index 3)以降を走査し、変換および切り取りを行う
        last_numeric_col = 3
        for col_idx in range(3, schedule.shape[1]):
            val = schedule.iloc[0, col_idx]
            try:
                # 数値変換可能なら変換
                f_val = float(val)
                schedule.iloc[0, col_idx] = format_time(f_val)
                last_numeric_col = col_idx
            except (ValueError, TypeError):
                # 文字列が現れた時点で停止し、それ以降の列を切り取る
                schedule = schedule.iloc[:, :col_idx]
                break
        
        location_data[key] = schedule
        
    return location_data

# 3. メイン処理（既存の認証・読み込み部分は維持）
# ... (get_service, load_and_process_dataは既存のものを利用) ...

st.title("シフト時程表ビューワー")

try:
    data_dict = load_and_process_data()
    
    st.subheader("勤務地を選択してください")
    
    # 横並びのボタン形式
    cols = st.columns(len(data_dict))
    selected_key = None
    for i, key in enumerate(data_dict.keys()):
        if cols[i].button(key):
            selected_key = key
    
    # 選択後の表示
    if selected_key:
        st.divider()
        st.write(f"### {selected_key} の勤務詳細")
        st.dataframe(data_dict[selected_key], hide_index=True, use_container_width=True)

except Exception as e:
    st.error(f"データの読み込み中にエラーが発生しました: {e}")
