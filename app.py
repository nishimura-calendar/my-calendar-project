import streamlit as st
import gspread
from google.oauth2.credentials import Credentials

st.title("認証テスト")

try:
    # 辞書として取得できているか確認
    creds_dict = st.secrets["google_oauth_credentials"]
    st.write("Secrets取得成功")
    
    # 最小構成でCredentialsを作成
    creds = Credentials(
        token=creds_dict["token"],
        refresh_token=creds_dict["refresh_token"],
        token_uri=creds_dict["token_uri"],
        client_id=creds_dict["client_id"],
        client_secret=creds_dict["client_secret"]
    )
    
    st.write("Credentials作成成功")
    
    # スプレッドシート接続
    gc = gspread.authorize(creds)
    sh = gc.open_by_key("1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE")
    st.success("スプレッドシート接続成功！")

except Exception as e:
    st.error(f"エラー詳細: {e}")
