import streamlit as st
import os
import json
from practice_0 import generate_shift_csv
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

# 指定のフォルダID (シフトカレンダー.xlsxの設定値)
FOLDER_ID = "19GBObKKJQylZXLaxfApt3iSgA1893TKa"

def get_service():
    # Secretsから辞書全体を取得
    creds_dict = st.secrets["google_oauth_credentials"]
    
    # Credentialsに必要なキーが揃っているか確認し、生成する
    # Secretsがすでに辞書形式であればそのまま渡せます
    creds = Credentials.from_authorized_user_info(dict(creds_dict))
    
    return build('drive', 'v3', credentials=creds)

def save_to_drive(local_file_path, folder_id, file_name):
    service = get_service()
    file_metadata = {
        'name': file_name,
        'parents': [folder_id]
    }
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
            # 仮のデータ（本来はPDF解析結果を代入）
            key = "T1"
            staff_name = "山田太郎"
            dummy_shift_data = {"2026-06-21": "A"} # テストデータ
            dummy_time_dic = {"A": 9.0}
            
            # 1. CSV生成
            local_filename = generate_shift_csv(key, staff_name, dummy_shift_data, dummy_time_dic)
            
            # 2. ドライブ保存
            file_id = save_to_drive(local_filename, FOLDER_ID, local_filename)
            
            st.success(f"完了しました！ (File ID: {file_id})")
            
            # 一時ファイルの削除
            if os.path.exists(local_filename):
                os.remove(local_filename)

if __name__ == "__main__":
    main()
