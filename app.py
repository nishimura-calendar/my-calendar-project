import streamlit as st
import pandas as pd
import io
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# 1. 認証情報の取得
def get_service():
    creds_dict = st.secrets["google_oauth_credentials"]
    creds = Credentials(
        token=creds_dict["token"],
        refresh_token=creds_dict["refresh_token"],
        token_uri=creds_dict["token_uri"],
        client_id=creds_dict["client_id"],
        client_secret=creds_dict["client_secret"]
    )
    return build('drive', 'v3', credentials=creds)

# 2. 小数から時刻表記(H:MM)への変換関数
# 1. 小数から時刻表記(H:MM)への変換関数
def format_time(val):
    try:
        f_val = float(val)
        h = int(f_val)
        m = int(round((f_val - h) * 60))
        return f"{h}:{m:02d}"
    except (ValueError, TypeError):
        return val

# 2. データの読み込みと変換処理
@st.cache_data(ttl=600)
def load_and_process_data():
    # Excelファイルを読み込み (ヘッダーなし)
    df = pd.read_excel('時程表.xlsx', sheet_name='Table 1', header=None)
    
    # 全データをコピーして処理
    processed_df = df.copy()
    
    # 行ごとにD列(index 3)からスキャン
    for row_idx in range(processed_df.shape[0]):
        for col_idx in range(3, processed_df.shape[1]):
            val = processed_df.iloc[row_idx, col_idx]
            
            # 数値として解釈できるかチェック
            try:
                # 数値であれば変換を試みる
                float(val)
                processed_df.iloc[row_idx, col_idx] = format_time(val)
            except (ValueError, TypeError):
                # 数値でなくなった（文字が現れた）時点で、この行の変換を終了する
                break
            
    return processed_df

st.title("シフト時程表ビューワー")

try:
    df_processed = load_and_process_data()
    
    st.subheader("シフトを選択してください")
    
    # B列(index 1)をシフトコードとしてセレクトボックスを作成
    # 選択肢をユニークにし、リスト化
    shift_codes = df_processed.iloc[:, 1].dropna().astype(str).unique().tolist()
    selected_code = st.selectbox("シフトを選択", shift_codes)
            
    if selected_code:
        st.divider()
        st.write(f"### シフト {selected_code} の勤務詳細")
        
        # 選択されたコードに該当する行を抽出
        target_row = df_processed[df_processed.iloc[:, 1].astype(str) == selected_code]
        
        # データの表示 (indexは非表示にして見やすく)
        st.dataframe(target_row, hide_index=True, use_container_width=True)

except Exception as e:
    st.error(f"データの読み込み中にエラーが発生しました: {e}")
