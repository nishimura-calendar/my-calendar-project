import streamlit as st
import datetime
import os
import json
from practice_0 import generate_shift_csv
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account

# SecretsからJSONを読み込む
def get_service():
    creds_dict = st.secrets["gcp_service_account"]
    creds = service_account.Credentials.from_service_account_info(creds_dict)
    return build('drive', 'v3', credentials=creds)

FOLDER_ID = "19GBObKKJQylZXLaxfApt3iSgA1893TKa"

def save_to_drive(local_file_path, folder_id, file_name):
    service = get_service()
    file_metadata = {
        'name': file_name,
        'parents': [folder_id]
    }
    media = MediaFileUpload(local_file_path, mimetype='text/csv')
    file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    return file.get('id')

def main():
    st.title("シフトカレンダー作成システム")
    uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")
    
    if uploaded_file:
        key = "T1"
        staff_name = "山田太郎"
        
        if st.button("CSV生成と保存"):
            # ローカルにCSV生成
            local_filename = generate_shift_csv(key, staff_name, {}, {}) 
            
            try:
                # ドライブへアップロード
                file_id = save_to_drive(local_filename, FOLDER_ID, local_filename)
                st.success(f"ドライブに保存しました (ID: {file_id})")
            except Exception as e:
                st.error(f"アップロード失敗: {e}")
            finally:
                if os.path.exists(local_filename):
                    os.remove(local_filename)

if __name__ == "__main__":
    main()
