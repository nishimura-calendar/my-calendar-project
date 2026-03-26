import camelot
import pandas as pd
import pdfplumber
import re
import io
import unicodedata

def extract_year_month(pdf_stream):
    """PDFタイトルから年月を抽出"""
    with pdfplumber.open(pdf_stream) as pdf:
        text = pdf.pages[0].extract_text()
        for line in text.split('\n'):
            if "勤務予定表" in line or "月度" in line:
                m = re.search(r'(20\d{2})[年/]\s?(\d{1,2})', line)
                if m: return m.group(1), m.group(2)
    return "2026", "1"

def parse_special_shift(text):
    """
    '9@14' や '10.5@19' を解析して (開始, 終了, 成功フラグ) を返す
    西村さん専用の特殊時間入力対応ロジック
    """
    text = str(text).strip().replace(' ', '')
    if "@" in text:
        try:
            parts = text.split("@")
            s_val = float(parts[0])
            e_val = float(parts[1])
            # 小数点（.5）を分（30分）に変換
            start_t = f"{int(s_val):02d}:{int((s_val % 1) * 60):02d}"
            end_t = f"{int(e_val):02d}:{int((e_val % 1) * 60):02d}"
            return start_t, end_t, True
        except (ValueError, IndexError):
            return None, None, False
    return None, None, False

def time_schedule_from_drive(service, file_id):
    """Excelの時程表を取得"""
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
        col_limit = len(full_df.columns)
        for i in range(2, len(full_df.columns)):
            val = full_df.iloc[0, i]
            try: float(val)
            except: col_limit = i; break
        
        loc_idx = full_df[full_df.iloc[:, 0].astype(str).str.strip().replace('nan', '') != ""].index.tolist()
        for i, start_row in enumerate(loc_idx):
            loc_name = re.sub(r'[\s　]', '', str(full_df.iloc[start_row, 0]))
            end_row = loc_idx[i+1] if i+1 < len(loc_idx) else len(full_df)
            df = full_df.iloc[start_row:end_row, 0:col_limit].copy().reset_index(drop=True).fillna('')
            df.iloc[:, 1] = df.iloc[:, 1].astype(str).apply(lambda x: unicodedata.normalize('NFKC', x).strip())
            location_data_dic[loc_name] = df
    return location_data_dic

def pdf_reader(pdf_stream, target_staff):
    """PDFから自分と他人のデータを場所別に抽出"""
    clean_target = re.sub(r'[\s　]', '', str(target_staff))
    with open("temp.pdf", "wb") as f: f.write(pdf_stream.getbuffer())
    
    tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    pdf_dic = {}
    for table in tables:
        df = table.df
        if df.empty: continue
        text = str(df.iloc[0, 0])
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        work_place = re.sub(r'[\s　]', '', lines[len(lines)//2]) if lines else "Unknown"
        
        df.iloc[:, 0] = df.iloc[:, 0].astype(str).str.replace(r'[\s　]', '', regex=True)
        matched = df.index[df.iloc[:, 0] == clean_target].tolist()
        if matched:
            idx = matched[0]
            # [自分の2行, 全員のデータ] を保持
            pdf_dic[work_place] = [df.iloc[idx:idx+2, :].copy(), df]
    return pdf_dic

def data_integration(pdf_dic, time_sched_dic):
    integrated = {}
    for key in pdf_dic.keys():
        if key in time_sched_dic:
            integrated[key] = pdf_dic[key] + [time_sched_dic[key]]
    return integrated
