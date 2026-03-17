import camelot
import pandas as pd
import pdfplumber
import re
import io

def pdf_reader(pdf_stream, target_staff):
    """PDFから自分と他人のシフトを抽出"""
    clean_target = str(target_staff).replace(' ', '').replace('　', '')
    
    # クラウド環境用の一時保存
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
        
    tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    table_dictionary = {}
    
    for table in tables:
        df = table.df
        if not df.empty:
            # --- 西村さんのオリジナル勤務地抽出ロジック ---
            text = str(df.iloc[0, 0])
            lines = text.splitlines()
            target_index = text.count('\n') // 2
            work_place = lines[target_index] if target_index < len(lines) else (lines[-1] if lines else "Unknown")
            
            # 名称の正規化 (Excel側との一致を担保)
            work_place = work_place.strip()
            if work_place == "1" or "第2ターミナル" in work_place: work_place = "T2"
            elif work_place == "2" or "第1ターミナル" in work_place: work_place = "T1"
            
            df.iloc[0, 0] = work_place
            df = df.fillna('')

            # 検索用列（スペース除去）
            search_col = df.iloc[:, 0].astype(str).str.replace(r'[\s　]', '', regex=True)
            matched_indices = df.index[search_col == clean_target].tolist()
        
            if matched_indices:
                idx = matched_indices[0]
                # 自分(2行分)とそれ以外を抽出
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
    location_rows = full_df[full_df.iloc[:, 0].notna()].index.tolist()
    location_data_dic = {}
    
    for i, start_row in enumerate(location_rows):
        end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
        location_name = str(full_df.iloc[start_row, 0]).strip()
        data_range = full_df.iloc[start_row:end_row, 0:70].copy().reset_index(drop=True).astype(object)

        # 時間表記変換 (0.375 -> 9:00)
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
