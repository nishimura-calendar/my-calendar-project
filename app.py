import streamlit as st
import os
import json
from practice_0 import generate_shift_csv
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

# 設定値
FOLDER_ID = "19GBObKKJQylZXLaxfApt3iSgA1893TKa"
SPREADSHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

def get_service(api_name, version):
    creds_dict = st.secrets["google_oauth_credentials"]
    
    # 権限スコープを明示的に指定
    scopes = [
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/spreadsheets.readonly" # これを追加
    ]
    
    creds = Credentials.from_authorized_user_info(dict(creds_dict), scopes=scopes)
    return build(api_name, version, credentials=creds)
    
def load_time_schedule():
    """スプレッドシートから時程表を読み込む"""
    try:
        service = get_service('sheets', 'v4')
        
        # 1. まずスプレッドシート全体の情報を取得して、最初のシート名を取得する
        spreadsheet = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
        sheet_name = spreadsheet['sheets'][0]['properties']['title'] # 最初のシート名を自動取得
        
        # 2. そのシート名を使ってデータを取得
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID, 
            range=f"'{sheet_name}'!A1:C50").execute() # シングルクォーテーションで囲む
        
        values = result.get('values', [])
        time_dic = {f"{row[0]}_{row[1]}": row[2] for row in values if len(row) >= 3}
        return time_dic
    except Exception as e:
        st.error(f"読み込みエラー: {e}")
        return {}
        
def save_to_drive(local_file_path, folder_id, file_name):
    """CSVをGoogleドライブへアップロード"""
    service = get_service('drive', 'v3')
    file_metadata = {'name': file_name, 'parents': [folder_id]}
    media = MediaFileUpload(local_file_path, mimetype='text/csv')
    file = service.files().create(
        body=file_metadata, 
        media_body=media, 
        fields='id'
    ).execute()
    return file.get('id')

def main():
    if st.button("接続テスト"):
        try:
            service = get_service('sheets', 'v4')
            spreadsheet = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
            st.success(f"接続成功: {spreadsheet['properties']['title']}")
        except Exception as e:
            st.error(f"接続エラー: {e}")
            
if __name__ == "__main__":
    main()
