import camelot
import pandas as pd
import pdfplumber
import re
import io
import unicodedata

def time_schedule_from_drive(service, file_id):
    """場所名（A列）を起点に、表を切り出す（『記号』という文字がなくても動作）"""
    from googleapiclient.http import MediaIoBaseDownload
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done: _, done = downloader.next_chunk()
    fh.seek(0)
    
    excel_data = pd.read_excel(fh, sheet_name=None, header=None, engine='openpyxl')
    location_data_dic = {}
    
    for sheet_name, full_df in excel_data.items():
        if full_df.empty: continue

        # A列(index 0)が空ではない行を取得（場所名の開始行）
        location_rows = full_df[full_df.iloc[:, 0].astype(str).str.strip().replace('nan', '') != ""].index.tolist()

        for i, start_row in enumerate(location_rows):
            location_name = str(full_df.iloc[start_row, 0]).strip()
            end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
            
            # --- 列境界の判定（データが入っている最後の列まで取得） ---
            last_col = 2
            for c in range(2, full_df.shape[1]):
                if pd.notna(full_df.iloc[start_row, c]) and str(full_df.iloc[start_row, c]).strip() != "":
                    last_col = c
            col_limit = last_col + 1

            # 表の切り出しとインデックス振り直し（0行目を時刻ヘッダーに固定）
            data_range = full_df.iloc[start_row : end_row, 0 : col_limit].copy()
            data_range = data_range.reset_index(drop=True)
            data_range = data_range.astype(object)

            # B列(記号列)の正規化
            if data_range.shape[1] > 1:
                data_range.iloc[:, 1] = data_range.iloc[:, 1].apply(
                    lambda x: unicodedata.normalize('NFKC', str(x)).strip() if pd.notna(x) and str(x) != 'nan' else ""
                )

            # 時刻表記の変換 (Excelシリアル値 0.375 -> 9:00 等)
            for col in range(2, data_range.shape[1]):
                val = data_range.iloc[0, col]
                if pd.notna(val) and isinstance(val, (int, float)):
                    try:
                        h = int(val * 24) if val < 1 else int(val)
                        m = int(round((val * 24 - h) * 60)) if val < 1 else 0
                        data_range.iloc[0, col] = f"{h}:{m:02d}"
                    except: continue
                
            data_range = data_range.fillna('')
            location_data_dic[location_name] = [data_range]
            
    return location_data_dic

def pdf_reader(pdf_stream, target_staff):
    """PDFから自分と他人のシフトを抽出"""
    clean_target = re.sub(r'[\s　]', '', str(target_staff))
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
    tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    
    res_my, res_other = pd.DataFrame(), pd.DataFrame()
    for table in tables:
        df = table.df
        if df.empty: continue
        search_col = df.iloc[:, 0].astype(str).str.replace(r'[\s　]', '', regex=True)
        matched = df.index[search_col == clean_target].tolist()
        if matched:
            idx = matched[0]
            res_my = df.iloc[idx:idx+2, :].copy() # 記号と時間の2行
            res_other = df.copy()
            break
    return res_my, res_other

def extract_year_month(pdf_stream):
    with pdfplumber.open(pdf_stream) as pdf:
        text = pdf.pages[0].extract_text()
        m = re.search(r'(\20\d{2})[年/](\d{1,2})', text)
        return m.groups() if m else ("2026", "3")
