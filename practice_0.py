import camelot
import pandas as pd
import pdfplumber
import re
import io
import datetime

def convert_excel_time(val):
    """Excelのシリアル値や数値を、HH:MM形式の文字列に変換する。異常値(150:00等)を防ぐ"""
    if pd.isna(val) or val == "":
        return ""
    if isinstance(val, datetime.time):
        return val.strftime("%H:%M")
    if isinstance(val, (int, float)):
        try:
            # シリアル値(0.0-1.0)の場合
            if 0 <= val < 1.0:
                total_seconds = int(round(val * 86400))
                h = total_seconds // 3600
                m = (total_seconds % 3600) // 60
                return f"{h}:{m:02d}"
            else:
                # 整数で時間が入力されている場合（15.0など）
                h = int(val)
                m = int(round((val - h) * 60))
                return f"{h % 24}:{m:02d}"
        except:
            pass
    return str(val).strip()

def pdf_reader(pdf_stream, target_staff):
    """PDFからスタッフの勤務行とそれ以外のスタッフ行を抽出する"""
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
                table_dictionary[work_place] = [df.iloc[idx : idx + 2, :].copy(), df.drop([0, idx, idx+1]).copy()]
    return table_dictionary

def extract_year_month(pdf_stream):
    """PDFから年月を抽出する"""
    with pdfplumber.open(pdf_stream) as pdf:
        text = "".join([page.extract_text() or "" for page in pdf.pages])
    match = re.search(r'(\d{4})\s*年\s*(\d{1,2})\s*月', text)
    return (match.group(1), match.group(2)) if match else ("2026", "3")

def time_schedule_from_drive(service, file_id):
    """Google Driveから時程表を読み込み、時刻軸をクレンジングする"""
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
        
        # インデックス2（3列目）以降の時間軸ヘッダーをHH:MMに変換
        for col in range(2, data_range.shape[1]):
            data_range.iloc[0, col] = convert_excel_time(data_range.iloc[0, col])
            
        location_data_dic[location_name] = [data_range.fillna('')]
    return location_data_dic

def data_integration(pdf_dic, time_schedule_dic):
    """勤務地でPDFデータと時程表を統合する"""
    integrated_dic = {}
    for key, pdf_val in pdf_dic.items():
        if key in time_schedule_dic:
            integrated_dic[key] = pdf_val + time_schedule_dic[key]
    return integrated_dic
