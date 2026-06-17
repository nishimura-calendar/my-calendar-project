import streamlit as st
import datetime
import os
from practice_0 import generate_shift_csv
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials  # ← ここを追加

# 修正部分：サービスアカウントからOAuth認証へ
def get_service():
    # Secretsから新しいキーを読み込む
    creds_dict = st.secrets["google_oauth_credentials"]
    # 辞書から認証情報を生成
    creds = Credentials.from_authorized_user_info(creds_dict)
    return build('drive', 'v3', credentials=creds)

# あとは既存の save_to_drive 関数などはそのまま使えます！
FOLDER_ID = "19GBObKKJQylZXLaxfApt3iSgA1893TKa"

def save_to_drive(local_file_path, folder_id, file_name):
    service = get_service()
    file_metadata = {
        'name': file_name,
        'parents': [folder_id]
    }
    media = MediaFileUpload(local_file_path, mimetype='text/csv')
    # あなた自身の権限で実行するため、容量制限エラーは発生しません
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
        key = "T1"
        staff_name = "山田太郎"
        
        if st.button("CSV生成と保存"):
            local_filename = generate_shift_csv(key, staff_name, {}, {}) 
            
            try:
                file_id = save_to_drive(local_filename, FOLDER_ID, local_filename)
                st.success(f"ドライブに保存しました！ (ID: {file_id})")
            except Exception as e:
                st.error(f"アップロード失敗: {e}")
            finally:
                if os.path.exists(local_filename):
                    os.remove(local_filename)

if __name__ == "__main__":
    main()
