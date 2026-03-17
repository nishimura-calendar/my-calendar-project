import camelot
import pandas as pd
import pdfplumber
import re
import io

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
            text = str(df.iloc[0, 0])
            lines = text.splitlines()
            target_index = text.count('\n') // 2
            work_place = lines[target_index] if target_index < len(lines) else (lines[-1] if lines else "Unknown")
            
            work_place = work_place.strip()
            # 場所名の名寄せ
            if work_place == "1" or "第2ターミナル" in work_place: work_place = "T2"
            elif work_place == "2" or "第1ターミナル" in work_place: work_place = "T1"
            
            df = df.fillna('')
            search_col = df.iloc[:, 0].astype(str).str.replace(r'[\s　]', '', regex=True)
            matched_indices = df.index[search_col == clean_target].tolist()
        
            if matched_indices:
                idx = matched_indices[0]
                # 0行目（ヘッダー）を除いて抽出
                my_daily_shift = df.iloc[idx : idx + 2, :].copy()
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
    """GoogleドライブからExcel時程表を読み込み"""
    from googleapiclient.http import MediaIoBaseDownload
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done: _, done = downloader.next_chunk()
    fh.seek(0)
    
    full_df = pd.read_excel(fh, header=None, engine='openpyxl')
    # T2や本町などのキーワードで場所を特定（1列目に文字がある行）
    location_rows = full_df[full_df.iloc[:, 0].notna()].index.tolist()
    location_data_dic = {}
    
    for i, start_row in enumerate(location_rows):
        end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
        location_name = str(full_df.iloc[start_row, 0]).strip()
        data_range = full_df.iloc[start_row:end_row, 0:70].copy().reset_index(drop=True)

        # 時間表記変換
        for col in range(1, data_range.shape[1]):
            val = data_range.iloc[0, col]
            if pd.notna(val) and isinstance(val, (int, float)) and val > 0:
                total_min = int(round(val * 24 * 60))
                data_range.iloc[0, col] = f"{total_min // 60}:{total_min % 60:02d}"
                
        location_data_dic[location_name] = [data_range.fillna('')]
    return location_data_dic

def data_integration(pdf_dic, time_schedule_dic):
    """PDFと時程表を結合"""
    integrated_dic = {}
    for key, pdf_data in pdf_dic.items():
        if key in time_schedule_dic:
            integrated_dic[key] = pdf_data + time_schedule_dic[key]
    return integrated_dic

def working_hours(text):
    match = re.search(r'([①-⑳])', text)
    if not match: return "", ""
    parts = re.split(r'[①-⑳]', text)
    return parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""
