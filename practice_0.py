import camelot
import numpy as np
import pandas as pd
import pdfplumber
import re
import io
from googleapiclient.http import MediaIoBaseDownload

def pdf_reader(pdf_stream, target_staff):
    """PDFから自分と他人のシフトを抽出"""
    clean_target = str(target_staff).replace(' ', '').replace('　', '')
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
        
    tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    table_dictionary = {}
    
    for table in tables:
        df = table.df
        if not df.empty:
            # 勤務地抽出（A1セルの1行目付近）
            text = str(df.iloc[0, 0])
            lines = text.splitlines()
            work_place = lines[0].strip() if lines else "Unknown"
            
            df = df.fillna('')
            search_col = df.iloc[:, 0].astype(str).str.replace(r'[\s　]', '', regex=True)
            
            target_row_index = search_col[search_col == clean_target].index
            if not target_row_index.empty:
                idx = target_row_index[0]
                my_daily_shift = df.iloc[idx : idx + 2, :]
                other_daily_shift = df.drop(df.index[idx : idx + 2])
                # [自分, 他人] のリストを保存
                table_dictionary[work_place] = [my_daily_shift, other_daily_shift]
                
    return table_dictionary

def extract_year_month(pdf_stream):
    """PDFから年月を抽出"""
    with pdfplumber.open(pdf_stream) as pdf:
        text = "".join([page.extract_text() or "" for page in pdf.pages])
    
    match = re.search(r'(\d{4})\s*年\s*(\d{1,2})\s*月', text)
    if match:
        return match.group(1), match.group(2)
    return "2026", "3"

def time_schedule_from_drive(service, file_id):
    """ドライブからExcel時程表を読み込み"""
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    fh.seek(0)
    
    try:
        full_df = pd.read_excel(fh, header=None, engine='openpyxl')
    except Exception as e:
        raise Exception(f"Excel読み取りエラー: {e}")
        
    location_data_dic = {}
    # T2や本町などのキーワードで場所を特定
    location_rows = full_df[full_df.iloc[:, 0].astype(str).str.contains(r'第[一二三四五]ターミナル|本町|T2', na=False, regex=True)].index

    for row_idx in location_rows:
        location_name = str(full_df.iloc[row_idx, 0]).strip()
        data_range = full_df.iloc[row_idx + 2 : row_idx + 8, 1:33].copy()
        
        # 時刻形式変換
        for col in range(data_range.shape[1]):
            val = data_range.iloc[0, col]
            if isinstance(val, (int, float)) and val > 0:
                total_minutes = int(round(val * 24 * 60))
                data_range.iloc[0, col] = f"{total_minutes // 60}:{total_minutes % 60:02d}"
                        
        data_range = data_range.fillna('')
        location_data_dic[location_name] = [data_range] # リストとして保存
        
    return location_data_dic

def data_integration(pdf_dic, time_schedule_dic):
    """PDFと時程表を結合"""
    integrated_dic = {}
    for key, pdf_data in pdf_dic.items():
        if key in time_schedule_dic:
            # [自分, 他人] + [時程表] -> [自分, 他人, 時程表]
            integrated_dic[key] = pdf_data + time_schedule_dic[key]
    return integrated_dic

def working_hours(text):
    match = re.search(r'([①-⑳])', text)
    if not match: return "", ""
    parts = re.split(r'[①-⑳]', text)
    return parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""
