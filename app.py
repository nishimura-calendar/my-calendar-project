import streamlit as st
import pandas as pd
import gspread
from google.oauth2.credentials import Credentials

st.title("最終デバッグ")

# Secretsの取得
try:
    creds_dict = st.secrets["google_oauth_credentials"]
    
    # 認証情報を作成
    creds = Credentials(
        token=creds_dict["token"],
        refresh_token=creds_dict["refresh_token"],
        token_uri=creds_dict["token_uri"],
        client_id=creds_dict["client_id"],
        client_secret=creds_dict["client_secret"]
    )
    
    # ここでトークンの有効期限を確認
    st.write(f"トークン有効期限: {creds.expiry}")
    
    # 強制的に更新を試みる
    from google.auth.transport.requests import Request
    creds.refresh(Request())
    st.write("トークンの更新成功！")
    
    # 接続
    gc = gspread.authorize(creds)
    sh = gc.open_by_key("1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE")
    st.success("スプレッドシートへの接続成功！")

except Exception as e:
    st.error(f"エラー詳細: {e}")
