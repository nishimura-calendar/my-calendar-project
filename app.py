import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# スプレッドシート読み込み関数
def load_time_schedule_from_sheets():
    # Secretsから認証情報を取得
    creds_dict = st.secrets["google_oauth_credentials"]
    
    # 認証スコープ
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc = gspread.authorize(creds)
    
    # 時程表のスプレッドシートID
    sheet_id = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"
    sh = gc.open_by_key(sheet_id)
    
    # 最初のシートを読み込む
    worksheet = sh.get_worksheet(0)
    data = worksheet.get_all_values()
    
    # DataFrameに変換（1行目を見出しとする）
    df = pd.DataFrame(data[1:], columns=data[0])
    return df

st.title("シフトカレンダー作成システム")

if st.button("時程表を読み込む"):
    try:
        with st.spinner("スプレッドシートからデータを取得しています..."):
            df = load_time_schedule_from_sheets()
            st.success("読み込み成功！")
            st.dataframe(df)
            st.session_state.time_schedule = df
    except Exception as e:
        st.error(f"読み込みエラー: {e}")
        st.info("※スプレッドシートの「共有」設定で、認証情報のメールアドレスに閲覧権限を与えているか確認してください。")
