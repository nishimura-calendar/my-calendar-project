import camelot
import pandas as pd
import pdfplumber
import re
import io
import numpy as np

def convert_excel_time(val):
    """Excelの数値を正しい時刻形式(HH:MM)に変換する"""
    if pd.isna(val) or val == "": return ""
    if isinstance(val, (int, float)):
        # 1未満（例: 0.25）なら24倍して時間に、1以上（例: 6.25）ならそのまま時間として扱う
        hours = val * 24 if val < 1 else val
        total_min = int(round(hours * 60))
        h = total_min // 60
        m = total_min % 60
        return f"{h:02d}:{m:02d}"
    return str(val)

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
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            work_place = re.sub(r'[\s　]', '', lines[len(lines)//2]) if lines else "Unknown"
            df = df.fillna('')
            search_col = df.iloc[:, 0].astype(str).str.replace(r'[\s　]', '', regex=True)
            matched_indices = df.index[search_col == clean_target].tolist()
            if matched_indices:
                idx = matched_indices[0]
                table_dictionary[work_place] = [df.iloc[idx : idx + 2, :].copy(), df[(search_col != clean_target) & (df.index != 0)].copy()]
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
        raw_name = str(full_df.iloc[start_row, 0])
        location_name = re.sub(r'[\s　]', '', raw_name)
        data_range = full_df.iloc[start_row:end_row, 0:70].copy().reset_index(drop=True)
        # 時間行（通常は0行目）を変換
        for col in range(1, data_range.shape[1]):
            data_range.iloc[0, col] = convert_excel_time(data_range.iloc[0, col])
        location_data_dic[location_name] = [data_range.fillna('')]
    return location_data_dic

def data_integration(pdf_dic, time_schedule_dic):
    integrated_dic = {}
    for key, pdf_data in pdf_dic.items():
        if key in time_schedule_dic:
            integrated_dic[key] = pdf_data + time_schedule_dic[key]
    return integrated_dic
