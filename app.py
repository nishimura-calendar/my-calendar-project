import streamlit as st
import pandas as pd
import gspread
from google.oauth2.credentials import Credentials

st.title("デバッグ用：読み込みテスト")

try:
    # 1. Secretsの取得を試みる
    if "google_oauth_credentials" not in st.secrets:
        st.error("Secretsに 'google_oauth_credentials' が設定されていません。")
        st.stop()
        
    creds_dict = st.secrets["google_oauth_credentials"]
    st.write("1. Secretsの読み込み成功")
    
    # 2. 認証情報の作成
    creds = Credentials(
        token=creds_dict["token"],
        refresh_token=creds_dict["refresh_token"],
        token_uri=creds_dict["token_uri"],
        client_id=creds_dict["client_id"],
        client_secret=creds_dict["client_secret"]
    )
    st.write("2. 認証オブジェクト作成成功")
    
    # 3. スプレッドシート接続
    gc = gspread.authorize(creds)
    sheet_id = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"
    sh = gc.open_by_key(sheet_id)
    st.write("3. スプレッドシートへのアクセス成功")
    
    # 4. データ読み込み
    worksheet = sh.get_worksheet(0)
    data = worksheet.get_all_values()
    df = pd.DataFrame(data[1:], columns=data[0])
    
    st.success("読み込み成功！")
    st.dataframe(df)

except Exception as e:
    # エラーが出た場合、詳細を表示
    st.error(f"エラーが発生しました: {e}")
