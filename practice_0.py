import camelot
import pandas as pd
import pdfplumber
import re
import io
import datetime

def pdf_reader(pdf_stream, target_staff):
    clean_target = str(target_staff).replace(' ', '').replace('　', '')
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
                # idx: シフトコード(C等), idx+1: 勤務記号(○等)
                table_dictionary[work_place] = [df.iloc[idx : idx + 2, :].copy(), df.drop([0, idx, idx+1]).copy()]
    return table_dictionary

def extract_year_month(pdf_stream):
    with pdfplumber.open(pdf_stream) as pdf:
        text = "".join([page.extract_text() or "" for page in pdf.pages])
    match = re.search(r'(\d{4})\s*年\s*(\d{1,2})\s*月', text)
    return (match.group(1), match.group(2)) if match else ("2026", "3")

def time_schedule_from_drive(service, file_id):
    from googleapiclient.http import MediaIoBaseDownload
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
        location_name = str(full_df.iloc[start_row, 0]).replace(' ', '').replace('　', '')
        data_range = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
        
        # 0行目（時刻）のシリアル値を文字列に変換
        for col in range(2, data_range.shape[1]):
            val = data_range.iloc[0, col]
            if isinstance(val, (int, float)) and val < 1.0:
                hours = int(val * 24)
                minutes = int(round((val * 24 - hours) * 60))
                data_range.iloc[0, col] = f"{hours}:{minutes:02d}"
            elif isinstance(val, datetime.time):
                data_range.iloc[0, col] = val.strftime("%H:%M")
        
        location_data_dic[location_name] = [data_range.fillna('')]
    return location_data_dic

def data_integration(pdf_dic, time_schedule_dic):
    for key, value in time_schedule_dic.items():
        if key in pdf_dic:
            pdf_dic[key].extend(value)
    return pdf_dic
