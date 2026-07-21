import streamlit as st
import pandas as pd
import io
import camelot
import re
import calendar
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.credentials import Credentials

# 設定
SPREADSHEET_ID = '1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE'

def get_service():
    """Google Drive API認証"""
    creds_dict = st.secrets["google_oauth_credentials"]
    creds = Credentials(**creds_dict)
    return build('drive', 'v3', credentials=creds)

def load_time_schedule():
    """[1] 時程表の読み込みと辞書登録"""
    service = get_service()
    request = service.files().export_media(fileId=SPREADSHEET_ID, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    downloader.next_chunk()
    fh.seek(0)
    
    df = pd.read_excel(fh, sheet_name="Table 1", header=None)
    
    time_schedules = {}
    current_key = None
    
    # 勤務地をkeyとして登録
    for _, row in df.iterrows():
        val = row.iloc[0]
        if pd.notna(val) and str(val).strip():
            current_key = str(val).strip()
            time_schedules[current_key] = []
        
        # 勤務値行以降の処理（ロジック適用）
        if current_key:
            data_row = []
            for col_idx in range(3, len(row)):
                cell = row.iloc[col_idx]
                if pd.isna(cell) or isinstance(cell, str):
                    break
                data_row.append(cell)
            time_schedules[current_key].append(data_row)
            
    return time_schedules

def get_pdf_metadata(file_path, file_name):
    """[2] <1> PDF解析・ブロック抽出・日付判定"""
    tables = camelot.read_pdf(file_path, pages='all', flavor='stream')
    full_df = pd.concat([t.df for t in tables], ignore_index=True)
    
    # 名前リストの定義（ブロック終了条件）
    names = ["田坂", "水野", "前田", "武輪"] 
    
    max_date = 0
    in_block = False
    block_data = []
    
    for _, row in full_df.iterrows():
        row_str = " ".join([str(v) for v in row])
        
        # key行開始判定
        if re.search(r'T[12]', row_str):
            in_block = True
            continue
            
        # 名前行到達でブロック終了判定
        if in_block and any(n in row_str for n in names):
            in_block = False
            continue
            
        # 対象範囲内の行のみ抽出
        if in_block:
            block_data.append(row_str)
            
    # 最大日付の抽出
    all_nums = [int(n) for line in block_data for n in re.findall(r'\d+', line) if 1 <= int(n) <= 31]
    max_date = max(all_nums) if all_nums else 0
    
    # 最終曜日の算出
    match = re.search(r'(\d{4})年?(\d{1,2})月', file_name)
    year = int(match.group(1)) if match else datetime.now().year
    month = int(match.group(2)) if match else datetime.now().month
    last_weekday = ["月", "火", "水", "木", "金", "土", "日"][calendar.weekday(year, month, max_date)]
    
    return max_date, last_weekday

# 実行
if __name__ == "__main__":
    # 1. 辞書登録
    schedule_dict = load_time_schedule()
    
    # 2. PDF解析 (ファイルアップロードがある前提)
    # max_date, last_weekday = get_pdf_metadata(path, name)
