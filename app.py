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
    """認証情報を取得してGoogle APIサービスを構築"""
    creds_dict = st.secrets["google_oauth_credentials"]
    # 辞書形式で認証情報を生成
    creds = Credentials.from_authorized_user_info(dict(creds_dict))
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
    st.title("シフトカレンダー作成システム")
    uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")
    
    if uploaded_file:
        st.write("ファイルを確認しました。")
        
        if st.button("CSV生成とGoogleドライブへ保存"):
            # 1. 時程表の読み込み
            with st.spinner('時程表を読み込み中...'):
                time_dic = load_time_schedule()
            
            # 2. PDF解析・CSV生成
            # (現在はテストデータを使用。今後ここをPDF解析結果に差し替えます)
            key = "T1"
            staff_name = "山田太郎"
            dummy_shift_data = {"2026-06-21": "A"} 
            
            local_filename = generate_shift_csv(key, staff_name, dummy_shift_data, time_dic)
            
            # 3. ドライブ保存
            file_id = save_to_drive(local_filename, FOLDER_ID, local_filename)
            st.success(f"完了しました！ (File ID: {file_id})")
            
            # 一時ファイルの削除
            if os.path.exists(local_filename):
                os.remove(local_filename)

if __name__ == "__main__":
    main()
