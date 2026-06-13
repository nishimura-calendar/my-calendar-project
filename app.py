import streamlit as st
import datetime
import os # 追加しました
from practice_0 import generate_shift_csv
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

creds = None # ここには実際の認証オブジェクトが必要です

# 定数
FOLDER_ID = "19GBObKKJQylZXLaxfApt3iSgA1893TKa"

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
            # 1. ローカルにCSVを作成し、ファイル名を取得
            local_filename = generate_shift_csv(key, staff_name, {}, {}) 
            
            # 2. 生成されたファイルをドライブへアップロード
            try:
                save_to_drive(local_filename, FOLDER_ID, local_filename)
                st.success(f"{local_filename} をドライブに保存しました！")
            except Exception as e:
                st.error(f"アップロード失敗: {e}")
            finally:
                # 3. アップロード後はローカルのゴミを掃除
                if os.path.exists(local_filename):
                    os.remove(local_filename)
                    
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
