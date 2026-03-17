import camelot
import pandas as pd
import pdfplumber
import re
import io
import numpy as np

def pdf_reader(pdf_stream, target_staff):
    """PDFから場所名を抽出し、空白を完全除去して自分と他人のシフトを抽出"""
    # 検索対象の名前から空白を除去
    clean_target = re.sub(r'[\s　]', '', str(target_staff))
    
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
        
    # flavor='lattice' で罫線を解析
    tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    table_dictionary = {}
    
    for table in tables:
        df = table.df
        if not df.empty:
            # 1. セル(0,0)のテキストから「中身のある行」だけを抽出
            text = str(df.iloc[0, 0])
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            
            if lines:
                # 2. リストの中央付近を場所名として取得
                target_idx = len(lines) // 2
                raw_place = lines[target_idx]
                # 3. 場所名から空白・改行を完全に除去
                work_place = re.sub(r'[\s　]', '', raw_place)
            else:
                work_place = "Unknown"

            df = df.fillna('')
            # 4. 0列目（名前列）からも空白を除去して一致判定
            search_col = df.iloc[:, 0].astype(str).str.replace(r'[\s　]', '', regex=True)
            matched_indices = df.index[search_col == clean_target].tolist()
        
            if matched_indices:
                idx = matched_indices[0]
                # 自分の2行（シフト名とコード）
                my_daily_shift = df.iloc[idx : idx + 2, :].copy()
                # 他人のスタッフ
                other_daily_shift = df[(search_col != clean_target) & (df.index != 0)].copy()

                table_dictionary[work_place] = [
                    my_daily_shift.reset_index(drop=True), 
                    other_daily_shift.reset_index(drop=True)
                ]
                
    return table_dictionary

def extract_year_month(pdf_stream):
    """PDFから年月を抽出"""
    with pdfplumber.open(pdf_stream) as pdf:
        text = "".join([page.extract_text() or "" for page in pdf.pages])
    match = re.search(r'(\d{4})\s*年\s*(\d{1,2})\s*月', text)
    if match: return match.group(1), match.group(2)
    return "2026", "3"

def time_schedule_from_drive(service, file_id):
    """GoogleドライブからExcel時程表を読み込み、場所名の空白を除去"""
    from googleapiclient.http import MediaIoBaseDownload
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done: _, done = downloader.next_chunk()
    fh.seek(0)
    
    full_df = pd.read_excel(fh, header=None, engine='openpyxl')
    # A列が空でない行を場所の開始位置とする
    location_rows = full_df[full_df.iloc[:, 0].notna()].index.tolist()
    location_data_dic = {}
    
    for i, start_row in enumerate(location_rows):
        end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
        
        # Excel側の場所名からも空白を完全に除去
        raw_name = str(full_df.iloc[start_row, 0])
        location_name = re.sub(r'[\s　]', '', raw_name)
        
        data_range = full_df.iloc[start_row:end_row, 0:70].copy().reset_index(drop=True)

        # 時間形式の変換
        for col in range(1, data_range.shape[1]):
            val = data_range.iloc[0, col]
            if pd.notna(val) and isinstance(val, (int, float)) and val > 0:
                total_min = int(round(val * 24 * 60))
                data_range.iloc[0, col] = f"{total_min // 60}:{total_min % 60:02d}"
                
        location_data_dic[location_name] = [data_range.fillna('')]
    return location_data_dic

def data_integration(pdf_dic, time_schedule_dic):
    """PDFと時程表を、空白除去済みの場所名キーで結合"""
    integrated_dic = {}
    for key, pdf_data in pdf_dic.items():
        if key in time_schedule_dic:
            # pdf_data[0]:自分のシフト, [1]:他人のシフト, [2]:Excelの時程
            integrated_dic[key] = pdf_data + time_schedule_dic[key]
    return integrated_dic
