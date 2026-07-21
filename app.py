import streamlit as st
import pandas as pd
import io
import camelot
import re
import calendar
from datetime import datetime
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import googleapiclient.http

# スプレッドシートID
SPREADSHEET_ID = '1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE'

def get_service():
    """Google Drive API認証"""
    creds_dict = st.secrets["google_oauth_credentials"]
    creds = Credentials(**creds_dict)
    return build('drive', 'v3', credentials=creds)

def load_time_schedule():
    """[1] 時程表読込の要件を実装"""
    service = get_service()
    request = service.files().export_media(fileId=SPREADSHEET_ID, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    fh = io.BytesIO()
    downloader = googleapiclient.http.MediaIoBaseDownload(fh, request)
    downloader.next_chunk()
    fh.seek(0)
    
    # <1> A列:勤務値, B列:シフトコード, C列:ロッカー の構造を想定
    df = pd.read_excel(fh, sheet_name="Table 1")
    
    time_schedules = {}
    current_key = None
    
    # <2> 勤務地をkeyとして登録し、D列以降（文字列が現れるまで）を処理
    for _, row in df.iterrows():
        if pd.notna(row[0]) and str(row[0]).strip():
            current_key = str(row[0]).strip()
            time_schedules[current_key] = []
        
        if current_key:
            schedule_data = []
            for col in range(3, len(row)): # D列(index 3)から開始
                val = row[col]
                if pd.isna(val) or isinstance(val, str):
                    break
                schedule_data.append(val)
            time_schedules[current_key].append(schedule_data)
            
    return time_schedules

def get_pdf_metadata(file_path, file_name):
    """ロジック遵守: key行以下・名前行より上の行から最大日付と曜日を抽出"""
    tables = camelot.read_pdf(file_path, pages='all', flavor='stream')
    df = pd.concat([t.df for t in tables], ignore_index=True)
    
    all_dates = []
    # 簡易的に全行を走査し、日付列と思われる数字を抽出
    for _, row in df.iterrows():
        text_row = " ".join([str(val) for val in row])
        nums = [int(n) for n in re.findall(r'\d+', text_row) if 1 <= int(n) <= 31]
        all_dates.extend(nums)
    
    max_date = max(all_dates) if all_dates else 0
    
    # 年月取得
    match = re.search(r'(\d{4})年?(\d{1,2})月', file_name)
    year = int(match.group(1)) if match else datetime.now().year
    month = int(match.group(2)) if match else datetime.now().month
    
    # 最終曜日算出
    last_weekday = ["月", "火", "水", "木", "金", "土", "日"][calendar.weekday(year, month, max_date)]
    return max_date, last_weekday

# メイン処理の入り口例
def main():
    st.title("シフト整合性チェックシステム")
    uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")
    
    if uploaded_file:
        with open("temp.pdf", "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        max_date, last_weekday = get_pdf_metadata("temp.pdf", uploaded_file.name)
        st.write(f"抽出結果 - 最大日付: {max_date}日, 最終曜日: {last_weekday}曜日")
        
        # 時程表データ読み込み
        schedule = load_time_schedule()
        # ここで整合性チェックロジックを続ける

if __name__ == "__main__":
    main()
