import pdfplumber
import pandas as pd
import io
import re

def normalize_text(text):
    """全角英数字を半角に、空白を除去する共通処理"""
    if not isinstance(text, str): return text
    return text.translate(str.maketrans('ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ０１２３４５６７８９', 
                                     'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')).strip()

def extract_year_month_from_text(text):
    """ファイル名から年、月を抽出"""
    match = re.search(r'(\d{4})[年._](\d{1,2})', text)
    if match:
        return match.groups()
    return "2026", "04" # デフォルト

def time_schedule_from_drive(service, file_id):
    """スプレッドシートの全シートを読み込み、勤務地ごとの辞書を返す"""
    # スプレッドシートのメタデータを取得してシート名リストを作る
    spreadsheet = service.files().get(fileId=file_id, fields='name').execute()
    # Sheets APIを使って値を読み取る (実際にはapp.pyで成功した方式を関数化)
    # ここではシンプルに全データを取得するロジックを想定
    sheet_metadata = build('sheets', 'v4', credentials=service._credentials).spreadsheets().get(spreadsheetId=file_id).execute()
    sheets = sheet_metadata.get('sheets', '')
    
    all_data = {}
    for s in sheets:
        title = s.get("properties", {}).get("title")
        result = build('sheets', 'v4', credentials=service._credentials).spreadsheets().values().get(
            spreadsheetId=file_id, range=f"'{title}'!A1:Z100").execute()
        vals = result.get('values', [])
        if vals:
            all_data[title] = pd.DataFrame(vals[1:], columns=vals[0])
    return all_data

def pdf_reader(pdf_file, target_name):
    """PDFを解析し、特定スタッフの勤務状況を抽出して返す"""
    results = {}
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                df = pd.DataFrame(table)
                # ここに西村様が作成された詳細な解析ロジック（shift_cal等）が入ります
                # 現時点では、読み込みテストのために簡易的なフィルタ結果を模しています
                # (実際にはお手元の practice_0 (11).py の中身をここに維持してください)
                
                # 仮の戻り値構造
                # results["勤務地名"] = [自分のDF, 他人のDF]
                pass 
    
    # ※実際にはここにお手元の practice_0 のメインロジックを配置してください
    return results # 解析結果の辞書
