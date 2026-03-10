import camelot
import numpy as np
import pandas as pd
import pdfplumber
import re
import io
from googleapiclient.http import MediaIoBaseDownload

def pdf_reader(pdf_stream, target_staff):
    """
    【クラウド版】PDFストリームからテーブルを読み込み、
    [自分(my_daily_shift), 自分以外(other_daily_shift)] のリストを辞書で返す。
    """
    # 比較用にスペースを除去
    clean_target = str(target_staff).replace(' ', '').replace('　', '')
    
    # クラウド環境では一時ファイルに書き出してからcamelotで読み込む
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
        
    tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    table_dictionary = {}
    
    for i, table in enumerate(tables):
        df = table.df
        if not df.empty:
            # --- 勤務地抽出ロジック ---
            text = str(df.iloc[0, 0])
            lines = text.splitlines()
            target_index = text.count('\n') // 2
            work_place = lines[target_index] if target_index < len(lines) else (lines[-1] if lines else "empty")
            df.iloc[0, 0] = work_place
            df = df.fillna('')

            # --- 検索用列の作成（スペース除去） ---
            search_col = df.iloc[:, 0].astype(str).str.replace(r'[\s　]', '', regex=True)

            # --- 抽出処理 ---
            target_row_index = search_col[search_col == clean_target].index
            if not target_row_index.empty:
                idx = target_row_index[0]
                my_daily_shift = df.iloc[idx : idx + 2, :]
                other_daily_shift = df.drop(df.index[idx : idx + 2])
                table_dictionary[work_place] = [my_daily_shift, other_daily_shift]
                
    return table_dictionary

def extract_year_month(pdf_stream):
    """PDF内のテキストから『〇〇〇〇年　〇月度』を抽出する"""
    with pdfplumber.open(pdf_stream) as pdf:
        text = ""
        for page in pdf.pages:
            text += page.extract_text() or ""
    
    match = re.search(r'(\d{4})\s*年\s*(\d{1,2})\s*月', text)
    if match:
        return match.group(1), match.group(2)
    return "2026", "1"  # デフォルト値

def time_schedule_from_drive(service, file_id):
    """
    【クラウド版】Google Drive上の時程表Excelを読み込み、場所ごとの辞書を返す
    """
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    fh.seek(0)
    
    full_df = pd.read_excel(fh, header=None)
    location_data_dic = {}
    
    # 場所名の入ったセル（例：A1, A10, A19...）を特定するロジック
    location_rows = full_df[full_df.iloc[:, 0].astype(str).str.contains('第[一二三四五]ターミナル|本町', na=False)].index

    for row_idx in location_rows:
        location_name = str(full_df.iloc[row_idx, 0]).strip()
        data_range = full_df.iloc[row_idx + 2 : row_idx + 8, 1:33].copy()
        
        # 数値を時刻形式 (H:MM) に変換
        for col in range(data_range.shape[1]):
            val = data_range.iloc[0, col]
            if isinstance(val, (int, float)) and val > 0:
                try:
                    total_minutes = int(round(val * 24 * 60))
                    hours = total_minutes // 60
                    minutes = total_minutes % 60
                    data_range.iloc[0, col] = f"{hours}:{minutes:02d}"
                except:
                    continue
                    
        data_range = data_range.fillna('')
        location_data_dic[location_name] = [data_range]
        
    return location_data_dic

def data_integration(pdf_dic, time_schedule_dic):
    """シフト内容と時程表を統合する"""
    for key, value in time_schedule_dic.items():
        if key in pdf_dic:
            pdf_dic[key].extend(value)
        else:
            print(f"{key}のシフト内容が届いていません。")
    return pdf_dic

def working_hours(text):
    """文字列から丸数字前後の時間を抽出"""
    match = re.search(r'([①-⑳])', text)
    if not match:
        return "", ""
    
    parts = re.split(r'[①-⑳]', text)
    start = parts[0].strip() if len(parts) > 0 else ""
    end = parts[1].strip() if len(parts) > 1 else ""
    return start, end
