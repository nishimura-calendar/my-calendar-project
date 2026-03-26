import camelot
import pandas as pd
import pdfplumber
import re
import io
import unicodedata

def time_schedule_from_drive(service, file_id):
    from googleapiclient.http import MediaIoBaseDownload
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    fh.seek(0)
    
    excel_data = pd.read_excel(fh, sheet_name=None, header=None, engine='openpyxl')
    location_dic = {}
    for _, full_df in excel_data.items():
        if full_df.empty: continue
        loc_rows = full_df[full_df.iloc[:, 0].astype(str).str.strip().replace('nan', '') != ""].index.tolist()
        for i, start_row in enumerate(loc_rows):
            loc_name = str(full_df.iloc[start_row, 0]).strip()
            end_row = loc_rows[i+1] if i+1 < len(loc_rows) else len(full_df)
            df = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True).fillna('')
            df.iloc[:, 1] = df.iloc[:, 1].astype(str).apply(lambda x: unicodedata.normalize('NFKC', x).strip())
            location_dic[loc_name] = df
    return location_dic

def pdf_reader(pdf_stream, target_staff):
    clean_target = re.sub(r'[\s　]', '', str(target_staff))
    with open("temp.pdf", "wb") as f: f.write(pdf_stream.getbuffer())
    tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    for table in tables:
        df = table.df
        search_col = df.iloc[:, 0].astype(str).str.replace(r'[\s　]', '', regex=True)
        matched = df.index[search_col == clean_target].tolist()
        if matched:
            # 自分の行(名前の行)とその下の行(記号の行)をセットで返す
            return df.iloc[matched[0] : matched[0]+2, :].copy(), df
    return pd.DataFrame(), pd.DataFrame()

def extract_year_month(pdf_stream):
    """PDFから『2026年1月度』というタイトルの年月を確実に抽出する"""
    with pdfplumber.open(pdf_stream) as pdf:
        text = pdf.pages[0].extract_text()
        # タイトル付近にある「202X年X月」という形式を、作成日(2025/12/27)より優先して探す
        lines = text.split('\n')
        for line in lines:
            if "勤務予定表" in line or "月度" in line:
                m = re.search(r'(20\d{2})[年/]\s?(\d{1,2})', line)
                if m:
                    return m.group(1), m.group(2)
        
        # 見つからない場合の予備（テキスト全体から最初に出現する2026年以降の日付を探す）
        m = re.search(r'(202[6-9])[年/]\s?(\d{1,2})', text)
        if m:
            return m.group(1), m.group(2)
            
    return "2026", "1" # 最終手段
