import camelot
import pandas as pd
import pdfplumber
import re
import io
import unicodedata

def time_schedule_from_drive(service, file_id):
    """Googleドライブから時程表を取得し、場所ごとのDataFrameを辞書形式で返す"""
    from googleapiclient.http import MediaIoBaseDownload
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    fh.seek(0)
    
    excel_data = pd.read_excel(fh, sheet_name=None, header=None, engine='openpyxl')
    location_data_dic = {}
    
    for sheet_name, full_df in excel_data.items():
        if full_df.empty: continue
        # A列に文字が入っている行を「場所の開始行」とみなす
        location_rows = full_df[full_df.iloc[:, 0].astype(str).str.strip().replace('nan', '') != ""].index.tolist()

        for i, start_row in enumerate(location_rows):
            location_name = str(full_df.iloc[start_row, 0]).strip()
            end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
            
            # 列の読み取り範囲を決定（時刻が入っている最終列まで）
            valid_cols = [c for c in range(2, full_df.shape[1]) if pd.notna(full_df.iloc[start_row, c])]
            col_limit = max(valid_cols) + 1 if valid_cols else full_df.shape[1]

            # 表の切り出しと整形
            data_range = full_df.iloc[start_row : end_row, 0 : col_limit].copy()
            data_range = data_range.reset_index(drop=True)
            
            # B列（記号）の正規化
            data_range.iloc[:, 1] = data_range.iloc[:, 1].astype(str).apply(
                lambda x: unicodedata.normalize('NFKC', x).strip()
            )

            # 0行目の時刻シリアル値を "HH:MM" 形式に変換
            for col in range(2, data_range.shape[1]):
                val = data_range.iloc[0, col]
                if isinstance(val, (int, float)) and val < 1:
                    h = int(val * 24)
                    m = int(round((val * 24 - h) * 60))
                    data_range.iloc[0, col] = f"{h}:{m:02d}"
                else:
                    data_range.iloc[0, col] = str(val).strip()
            
            location_data_dic[location_name] = [data_range.fillna('')]
            
    return location_data_dic

def pdf_reader(pdf_stream, target_staff):
    """PDFから指定スタッフの2行（記号・時間）と他全員のデータを抽出"""
    clean_target = re.sub(r'[\s　]', '', str(target_staff))
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    res_my, res_other = pd.DataFrame(), pd.DataFrame()
    
    for table in tables:
        df = table.df
        search_col = df.iloc[:, 0].astype(str).str.replace(r'[\s　]', '', regex=True)
        matched = df.index[search_col == clean_target].tolist()
        if matched:
            idx = matched[0]
            res_my = df.iloc[idx : idx+2, :].copy()
            res_other = df.copy()
            break
    return res_my, res_other

def extract_year_month(pdf_stream):
    """PDFテキストから年月を抽出"""
    with pdfplumber.open(pdf_stream) as pdf:
        text = pdf.pages[0].extract_text()
        # 修正後（\を消して 20 という数字にする）
        m = re.search(r'(20\d{2})[年/](\d{1,2})', text)
        return m.groups() if m else ("2026", "3")
