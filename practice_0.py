import pdfplumber
import pandas as pd
import io
import re
from googleapiclient.discovery import build  # 内部でbuildを使うため追加

def normalize_text(text):
    if not isinstance(text, str): return text
    return text.translate(str.maketrans('ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ０１２３４５６７８９', 
                                     'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')).strip()

def extract_year_month_from_text(text):
    match = re.search(r'(\d{4})[年._](\d{1,2})', text)
    if match: return match.groups()
    return "2026", "04"

def time_schedule_from_drive(service, file_id):
    """全シートを読み込む関数"""
    # serviceからcredentialsを取り出してSheets APIを構築
    sheets_service = build('sheets', 'v4', credentials=service._credentials)
    
    sheet_metadata = sheets_service.spreadsheets().get(spreadsheetId=file_id).execute()
    sheets = sheet_metadata.get('sheets', [])
    
    all_data = {}
    for s in sheets:
        title = s.get("properties", {}).get("title")
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=file_id, range=f"'{title}'!A1:Z100").execute()
        vals = result.get('values', [])
        if vals:
            all_data[title] = pd.DataFrame(vals[1:], columns=vals[0])
    return all_data

def pdf_reader(pdf_file, target_name):
    # ここに以前作成した解析ロジック（shift_cal等）を入れてください
    # 戻り値は { "勤務地": [自分のDF, 他人のDF] } の形式です
    results = {}
    # (中身の詳細は practice_0 (11).py を維持)
    return results
