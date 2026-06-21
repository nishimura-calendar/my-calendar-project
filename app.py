import streamlit as st
import os
import json
from practice_0 import generate_shift_csv
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

FOLDER_ID = "19GBObKKJQylZXLaxfApt3iSgA1893TKa"
# 時程表のスプレッドシートID
SPREADSHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

def get_service(api_name, version):
    creds_dict = st.secrets["google_oauth_credentials"]
    creds = Credentials.from_authorized_user_info(dict(creds_dict))
    return build(api_name, version, credentials=creds)

def load_time_schedule():
    """スプレッドシートから勤務地(key)をキーにして時程表を辞書化する"""
    service = get_service('sheets', 'v4')
    
    # 全シートを取得してループ処理（あるいは特定のシート名を指定）
    spreadsheet = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    sheet_name = spreadsheet['sheets'][0]['properties']['title'] # 最初のシートを対象
    
    # データ範囲を広めに取得
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range=f"{sheet_name}!A1:D50").execute()
    values = result.get('values', [])
    
    # 辞書生成ロジック
    # 想定: A列=勤務地(key), B列=シフトコード, C列=開始時間
    time_dic = {}
    for row in values:
        if len(row) >= 3:
            key = row[0]  # 勤務地
            shift = row[1] # シフトコード
            time = row[2]  # 時間
            time_dic[f"{key}_{shift}"] = time
            
    return time_dic

def save_to_drive(local_file_path, folder_id, file_name):
    service = get_service('drive', 'v3')
    file_metadata = {'name': file_name, 'parents': [folder_id]}
    media = MediaFileUpload(local_file_path, mimetype='text/csv')
    file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    return file.get('id')

def main():
    st.title("シフトカレンダー作成システム")
    uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")
    
    if uploaded_file:
        st.write("ファイルを確認しました。")
        
        if st.button("CSV生成とGoogleドライブへ保存"):
            # 1. スプレッドシートから時程表データを自動取得
            with st.spinner('時程表を読み込み中...'):
                time_dic = load_time_schedule()
            
            # 2. PDF解析・CSV生成 (※ここは引き続きPDF解析ロジックを実装)
            key = "T1"
            staff_name = "山田太郎"
            dummy_shift_data = {"2026-06-21": "A"} 
            
            local_filename = generate_shift_csv(key, staff_name, dummy_shift_data, time_dic)
            
            # 3. 保存
            file_id = save_to_drive(local_filename, FOLDER_ID, local_filename)
            st.success(f"完了しました！ (File ID: {file_id})")
            
            if os.path.exists(local_filename):
                os.remove(local_filename)

if __name__ == "__main__":
    main()
