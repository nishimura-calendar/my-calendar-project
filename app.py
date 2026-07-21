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

# --- 設定 ---
SPREADSHEET_ID = '1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE'

def get_service():
    """Google Drive API認証"""
    creds_dict = st.secrets["google_oauth_credentials"]
    creds = Credentials(**creds_dict)
    return build('drive', 'v3', credentials=creds)

@st.cache_data
def load_time_schedule():
    """[1] 時程表読み込みと辞書登録"""
    service = get_service()
    request = service.files().export_media(fileId=SPREADSHEET_ID, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    downloader.next_chunk()
    fh.seek(0)
    
    df = pd.read_excel(fh, sheet_name="Table 1", header=None)
    time_schedules = {}
    current_key = None
    
    for _, row in df.iterrows():
        val = row.iloc[0]
        if pd.notna(val) and str(val).strip():
            current_key = str(val).strip()
            time_schedules[current_key] = []
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
    """[2] <1> PDF解析・ブロック抽出・最大日付判定"""
    tables = camelot.read_pdf(file_path, pages='all', flavor='stream')
    full_df = pd.concat([t.df for t in tables], ignore_index=True)
    
    # ブロック終了の条件（名前行の検知）
    names = ["田坂", "水野", "前田", "武輪", "岸田", "米田", "奥村", "南川", "上條", "辻", "副島", "木村", "松岡", "上田", "友田", "春木", "塚田", "福川", "鈴木", "宮崎", "中尾"]
    
    max_date = 0
    in_block = False
    block_data = []
    
    for _, row in full_df.iterrows():
        row_str = " ".join([str(v) for v in row])
        
        # key行開始判定
        if re.search(r'T[12]', row_str):
            in_block = True
            continue
            
        # 名前行到達でブロック終了
        if in_block and any(n in row_str for n in names):
            in_block = False
            continue
            
        # 範囲内（key行以下、名前行より上）を抽出
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

# --- メインUI ---
def main():
    st.title("シフト整合性チェックシステム")
    
    # 1. 時程表辞書作成（バックグラウンド処理）
    try:
        schedule_dict = load_time_schedule()
    except Exception as e:
        st.error(f"時程表の読み込みエラー: {e}")
        return

    # 2. PDFアップロード
    uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")
    
    if uploaded_file is not None:
        with open("temp.pdf", "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        try:
            max_date, last_weekday = get_pdf_metadata("temp.pdf", uploaded_file.name)
            st.write(f"抽出結果 - 最大日付: {max_date}日, 最終曜日: {last_weekday}曜日")
        except Exception as e:
            st.error(f"解析中にエラーが発生しました: {e}")

if __name__ == "__main__":
    main()
