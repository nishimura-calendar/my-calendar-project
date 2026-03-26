import camelot
import pandas as pd
import pdfplumber
import re
import io
import unicodedata

def time_schedule_from_drive(service, file_id):
    """Googleドライブから時程表を取得し、場所名ごとに整形して返す"""
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
        # A列に文字がある行を「場所の開始」とみなす
        loc_rows = full_df[full_df.iloc[:, 0].astype(str).str.strip().replace('nan', '') != ""].index.tolist()

        for i, start_row in enumerate(loc_rows):
            loc_name = str(full_df.iloc[start_row, 0]).strip()
            end_row = loc_rows[i+1] if i+1 < len(loc_rows) else len(full_df)
            
            # 有効なデータ範囲を切り出し、B列（記号）を正規化
            df = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True).fillna('')
            df.iloc[:, 1] = df.iloc[:, 1].astype(str).apply(
                lambda x: unicodedata.normalize('NFKC', x).strip()
            )
            location_dic[loc_name] = df
            
    return location_dic

def pdf_reader(pdf_stream, target_staff):
    """PDFから指定スタッフの記号行と全体データを抽出"""
    clean_target = re.sub(r'[\s　]', '', str(target_staff))
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    for table in tables:
        df = table.df
        search_col = df.iloc[:, 0].astype(str).str.replace(r'[\s　]', '', regex=True)
        matched = df.index[search_col == clean_target].tolist()
        if matched:
            idx = matched[0]
            return df.iloc[idx : idx+2, :].copy(), df # 自分の2行, 全員分
    return pd.DataFrame(), pd.DataFrame()

def extract_year_month(pdf_stream):
    """PDFから年月を抽出（修正済み正規表現）"""
    with pdfplumber.open(pdf_stream) as pdf:
        text = pdf.pages[0].extract_text()
        m = re.search(r'(20\d{2})[年/](\d{1,2})', text)
        return m.groups() if m else ("2026", "3")
