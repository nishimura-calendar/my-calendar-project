import camelot
import pandas as pd
import pdfplumber
import re
import io
import numpy as np

def convert_excel_time(val):
    """Excelのシリアル値をHH:MM形式に正しく変換する"""
    if pd.isna(val) or val == "": return ""
    try:
        if isinstance(val, (int, float)):
            # 1未満ならシリアル値、1以上なら時間数として処理
            total_hours = val * 24 if val < 1 else val
            total_minutes = int(round(total_hours * 60))
            h = total_minutes // 60
            m = total_minutes % 60
            return f"{h}:{m:02d}"
    except:
        pass
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
            lines = text.splitlines()
            target_idx = len(lines) // 2
            work_place = re.sub(r'[\s　]', '', lines[target_idx]) if lines else "Unknown"
            df = df.fillna('')
            search_col = df.iloc[:, 0].astype(str).str.replace(r'[\s　]', '', regex=True)
            matched_indices = df.index[search_col == clean_target].tolist()
            if matched_indices:
                idx = matched_indices[0]
                # 自分の行(2行分)と、自分以外の行を保持
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
        location_name = re.sub(r'[\s　]', '', str(full_df.iloc[start_row, 0]))
        data_range = full_df.iloc[start_row:end_row, 0:70].copy().reset_index(drop=True)
        # 0行目(時間行)をHH:MMに変換
        for col in range(2, data_range.shape[1]):
            data_range.iloc[0, col] = convert_excel_time(data_range.iloc[0, col])
        location_data_dic[location_name] = [data_range.fillna('')]
    return location_data_dic

def data_integration(pdf_dic, time_schedule_dic):
    integrated_dic = {}
    for key, pdf_val in pdf_dic.items():
        if key in time_schedule_dic:
            integrated_dic[key] = pdf_val + time_schedule_dic[key]
    return integrated_dic
