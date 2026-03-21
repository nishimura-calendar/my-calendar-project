import camelot
import pandas as pd
import pdfplumber
import re
import io
import numpy as np

def extract_year_month(pdf_stream):
    """PDFから年月を抽出（ポインタを戻す処理を追加）"""
    pdf_stream.seek(0)
    with pdfplumber.open(pdf_stream) as pdf:
        text = "".join([page.extract_text() or "" for page in pdf.pages[:2]]) # 最初の2ページで十分
    match = re.search(r'(\d{4})\s*年\s*(\d{1,2})\s*月', text)
    pdf_stream.seek(0) # 次のcamelot処理のために戻す
    if match: return match.group(1), match.group(2)
    return "2026", "3"

def pdf_reader(pdf_stream, target_staff):
    clean_target = re.sub(r'[\s　]', '', str(target_staff))
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    table_dictionary = {}
    
    for table in tables:
        df = table.df
        if not df.empty:
            text = str(df.iloc[0, 0])
            lines = text.splitlines()
            target_idx = text.count('\n') // 2
            work_place = lines[target_idx] if target_idx < len(lines) else (lines[-1] if lines else "Unknown")
            
            df = df.fillna('')
            search_col = df.iloc[:, 0].astype(str).str.replace(r'[\s　]', '', regex=True)
            matched_indices = df.index[search_col == clean_target].tolist()
            if matched_indices:
                idx = matched_indices[0]
                # 名前行と、そのすぐ下の記号行をセットにする
                table_dictionary[work_place] = [df.iloc[idx : idx + 2, :].copy(), df.drop([0, idx, idx+1]).copy()]
    return table_dictionary

def time_schedule_from_drive(service, file_id):
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done: _, done = downloader.next_chunk()
    fh.seek(0)
    
    full_df = pd.read_excel(fh, header=None, engine='openpyxl')
    location_rows = full_df[full_df.iloc[:, 0].notna()].index.tolist()
    location_data_dic = {}
    
    for i, start_row in enumerate(location_rows):
        end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
        location_name = str(full_df.iloc[start_row, 0]).strip()
        
        # 時程表の列数（時刻が入っている範囲）を自動判定
        data_range = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
        data_range = data_range.astype(object)

        for col in range(2, data_range.shape[1]):
            val = data_range.iloc[0, col]
            if pd.notna(val) and isinstance(val, (int, float)) and val < 1.0:
                # Excelシリアル値 (0.5 = 12:00) を HH:MM に変換
                total_seconds = int(round(val * 86400))
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                data_range.iloc[0, col] = f"{hours}:{minutes:02d}"
        
        location_data_dic[location_name] = [data_range.fillna('')]
    return location_data_dic

def data_integration(pdf_dic, time_schedule_dic):
    for key, value in time_schedule_dic.items():
        if key in pdf_dic:
            pdf_dic[key].extend(value)
    return pdf_dic
