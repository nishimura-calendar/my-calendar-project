import camelot
import pandas as pd
import pdfplumber
import re
import io
import unicodedata

def extract_year_month(pdf_stream):
    """タイトル行から年月を抽出"""
    with pdfplumber.open(pdf_stream) as pdf:
        text = pdf.pages[0].extract_text()
        for line in text.split('\n'):
            if "勤務予定表" in line or "月度" in line:
                m = re.search(r'(20\d{2})[年/]\s?(\d{1,2})', line)
                if m: return m.group(1), m.group(2)
    return "2026", "1"

def time_schedule_from_drive(service, file_id):
    """Excelから場所ごとの時程表を取得し、col_limitで範囲を制限する"""
    from googleapiclient.http import MediaIoBaseDownload
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO(); downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done: _, done = downloader.next_chunk()
    fh.seek(0)
    
    excel_data = pd.read_excel(fh, sheet_name=None, header=None, engine='openpyxl')
    location_data_dic = {}
    
    for _, full_df in excel_data.items():
        if full_df.empty: continue
        
        # --- 【西村さん指定：列方向の範囲制限】 ---
        col_limit = len(full_df.columns)
        for i in range(2, len(full_df.columns)):
            val = full_df.iloc[0, i]
            try: float(val)
            except (ValueError, TypeError):
                col_limit = i
                break
        
        # A列の場所名を起点に分割
        loc_idx = full_df[full_df.iloc[:, 0].astype(str).str.strip().replace('nan', '') != ""].index.tolist()
        for i, start_row in enumerate(loc_idx):
            loc_name = str(full_df.iloc[start_row, 0]).strip()
            end_row = loc_idx[i+1] if i+1 < len(loc_idx) else len(full_df)
            
            df = full_df.iloc[start_row:end_row, 0:col_limit].copy().reset_index(drop=True).fillna('')
            # B列（記号）の正規化
            df.iloc[:, 1] = df.iloc[:, 1].astype(str).apply(lambda x: unicodedata.normalize('NFKC', x).strip())
            location_data_dic[loc_name] = df
    return location_data_dic

def pdf_reader(pdf_stream, target_staff):
    """PDFから【勤務地抽出ロジック】を用いて場所別に自分と他人のデータを保持"""
    clean_target = re.sub(r'[\s　]', '', str(target_staff))
    with open("temp.pdf", "wb") as f: f.write(pdf_stream.getbuffer())
    
    tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    pdf_dic = {}
    for table in tables:
        df = table.df
        if df.empty: continue
        
        # --- 【西村さん指定：勤務地抽出ロジック】 ---
        text = str(df.iloc[0, 0])
        lines = text.splitlines()
        target_index = text.count('\n') // 2
        work_place = lines[target_index] if target_index < len(lines) else (lines[-1] if lines else "empty")
        
        search_col = df.iloc[:, 0].astype(str).str.replace(r'[\s　]', '', regex=True)
        matched = df.index[search_col == clean_target].tolist()
        if matched:
            idx = matched[0]
            # { 勤務地: [自分の2行(本町対応用), テーブル全体] }
            pdf_dic[work_place] = [df.iloc[idx:idx+2, :].copy(), df]
    return pdf_dic

def data_integration(pdf_dic, time_sched_dic):
    """PDFの場所KeyとExcelの場所Keyを紐付けた辞書を作成"""
    integrated = {}
    for key in pdf_dic.keys():
        if key in time_sched_dic:
            # [自分の2行, テーブル全体, 時程表]
            integrated[key] = pdf_dic[key] + [time_sched_dic[key]]
    return integrated
