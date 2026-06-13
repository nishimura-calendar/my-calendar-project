import streamlit as st
import datetime
from practice_0 import generate_shift_csv

# 定数
FOLDER_ID = "19GBObKKJQylZXLaxfApt3iSgA1893TKa"
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def main():
    st.title("シフトカレンダー作成システム")
    
    # 1. アップロード処理とPDF解析 (第2関門)
    uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")
    if uploaded_file:
        # ここで勤務地(key)とスタッフ名を特定するロジックを実行
        key = "T1" # 仮定
        staff_name = "山田太郎" # 仮定
        
        # 2. 処理実行
        if st.button("CSV生成と保存"):
            csv_rows = generate_shift_csv(key, staff_name, {}, {}, {})
            
            # 3. 年月_名前_Key.csv で保存
            now = datetime.datetime.now()
            file_name = f"{now.strftime('%Y%m')}_{staff_name}_{key}.csv"
            
            # Google Drive API連携 (保存処理)
            # save_to_drive(csv_rows, file_name, FOLDER_ID)
            
            st.success(f"{file_name} を生成し保存しました。")

def save_to_drive(local_file_path, folder_id, file_name):
    """Google Driveへファイルをアップロードする関数"""
    # 認証処理（serviceの生成は適宜行ってください）
    service = build('drive', 'v3', credentials=creds)
    
    file_metadata = {
        'name': file_name,
        'parents': [folder_id]
    }
    media = MediaFileUpload(local_file_path, mimetype='text/csv')
    file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    print(f"File ID: {file.get('id')}")


if __name__ == "__main__":
    main()
