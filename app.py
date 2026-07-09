from google.oauth2.credentials import Credentials
import gspread

def load_time_schedule_from_sheets():
    # Streamlit Secretsから認証情報を取得
    creds_dict = st.secrets["google_oauth_credentials"]
    
    # ユーザー認証方式に変更（client_emailが不要な方式）
    creds = Credentials(
        token=creds_dict["token"],
        refresh_token=creds_dict["refresh_token"],
        token_uri=creds_dict["token_uri"],
        client_id=creds_dict["client_id"],
        client_secret=creds_dict["client_secret"]
    )
    
    # gspreadで認証
    gc = gspread.authorize(creds)
    
    # 時程表のスプレッドシートを開く
    sheet_id = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"
    sh = gc.open_by_key(sheet_id)
    
    # 最初のシートを読み込む
    worksheet = sh.get_worksheet(0)
    data = worksheet.get_all_values()
    
    # DataFrameに変換（1行目を見出しとする）
    df = pd.DataFrame(data[1:], columns=data[0])
    return df
