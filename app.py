import streamlit as st
import os
import json
import re
import calendar
import camelot
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

def get_b_from_pdf(pdf_file):
    """B: PDF内容から月末日を特定する"""
    tables = camelot.read_pdf(pdf_file, pages='1', flavor='stream')
    df = tables[0].df
    # 全データから数値を探し、最大値を月末日とする
    all_data = df.astype(str).values.flatten()
    days = [int(v) for v in all_data if v.strip().isdigit()]
    return max(days) if days else 0

def get_a_from_filename(filename):
    """A: ファイル名から年・月を特定し、その月の最終日を取得する"""
    year_match = re.search(r'20\d{2}', filename)
    month_match = re.search(r'(\d{1,2})月', filename)
    
    if year_match and month_match:
        year = int(year_match.group(0))
        month = int(month_match.group(1))
        _, last_day = calendar.monthrange(year, month)
        return last_day
    return None

def first_gate_check(uploaded_file):
    """第1関門：A=Bの検証"""
    filename = uploaded_file.name
    
    # B: 内容から取得
    last_day_b = get_b_from_pdf(uploaded_file)
    
    # A: ファイル名から取得
    last_day_a = get_a_from_filename(filename)
    
    if last_day_a is None:
        return False, "ファイル名から年・月が特定できませんでした。"
    
    if last_day_a != last_day_b:
        return False, f"整合性エラー: ファイル名からは{last_day_a}日までですが、PDF内容からは{last_day_b}日までとなっています。"
    
    return True, f"第1関門突破: {last_day_a}日までのデータとして確認しました。"
            
if __name__ == "__main__":
    main()
