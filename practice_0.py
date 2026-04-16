import pandas as pd
import pdfplumber
import camelot
import unicodedata
import re
import io
import calendar
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account

def get_gdrive_service(secrets):
    creds = service_account.Credentials.from_service_account_info(
        secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build('drive', 'v3', credentials=creds)

def extract_year_month_from_text(text):
    """テキスト（ファイル名など）から年月を抽出"""
    if not text: return None, None
    # 2026年1月, 2026/01, 26年1月 などのパターンに対応
    match = re.search(r'(\d{2,4})\s*[年/]\s*(\d{1,2})\s*月?', text)
    if match:
        y = int(match.group(1))
        if y < 100: y += 2000 # 26 -> 2026
        return y, int(match.group(2))
    return None, None

def extract_year_month_from_pdf(pdf_stream):
    """PDFの第1ページテキストから年月を抽出"""
    try:
        pdf_stream.seek(0)
        with pdfplumber.open(pdf_stream) as pdf:
            text = pdf.pages[0].extract_text()
            return extract_year_month_from_text(text)
    except: return None, None

def extract_max_day_from_pdf(pdf_stream):
    """PDFテーブルから最大の日付（月末日）を推測"""
    try:
        pdf_stream.seek(0)
        with open("temp_days.pdf", "wb") as f:
            f.write(pdf_stream.getbuffer())
        tables = camelot.read_pdf("temp_days.pdf", pages='1', flavor='lattice')
        if tables:
            df = tables[0].df
            # 1行目または2行目にある数値をすべて抽出して最大のものを探す
            all_text = " ".join(df.iloc[0:2, :].values.flatten().astype(str))
            days = re.findall(r'\b(2[89]|3[01])\b', all_text)
            if days:
                return int(max(days))
    except: pass
    return None

def extract_first_weekday_from_pdf(pdf_stream):
    """PDFテーブルの1日の列から曜日を抽出"""
    try:
        pdf_stream.seek(0)
        with open("temp_wd.pdf", "wb") as f:
            f.write(pdf_stream.getbuffer())
        tables = camelot.read_pdf("temp_wd.pdf", pages='1', flavor='lattice')
        if tables:
            df = tables[0].df
            # 1日のセル（通常2列目以降）から (月) などの文字を探す
            for col in range(1, min(6, df.shape[1])):
                cell_text = "".join(df.iloc[0:3, col].astype(str))
                match = re.search(r'[（\(]([月火水木金土日])[）\)]', cell_text)
                if match: return match.group(1)
    except: pass
    return None

def time_schedule_from_drive(service, file_id):
    request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done: _, done = downloader.next_chunk()
    fh.seek(0)
    full_df = pd.read_excel(fh, header=None, engine='openpyxl')
    
    location_rows = full_df[full_df.iloc[:, 0].notna()].index.tolist()
    dic = {}
    for i, start_row in enumerate(location_rows):
        end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
        name = str(full_df.iloc[start_row, 0]).strip()
        data = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
        for col in range(1, data.shape[1]):
            val = data.iloc[0, col]
            if pd.notna(val) and isinstance(val, (int, float)):
                h = int(val * 24)
                m = int(round((val * 24 - h) * 60))
                data.iloc[0, col] = f"{h}:{m:02d}"
        dic[name] = data.fillna('')
    return dic

def normalize_text(text):
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def pdf_reader(pdf_stream, target_staff):
    clean_target = normalize_text(target_staff)
    pdf_stream.seek(0)
    with open("temp_read.pdf", "wb") as f: f.write(pdf_stream.getbuffer())
    tables = camelot.read_pdf("temp_read.pdf", pages='all', flavor='lattice')
    res = {}
    for t in tables:
        df = t.df
        if df.empty: continue
        # 勤務地取得
        place = str(df.iloc[0, 0]).splitlines()[0]
        search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
        matches = df.index[search_col == clean_target].tolist()
        if matches:
            idx = matches[0]
            my = df.iloc[idx:idx+2, :].copy().reset_index(drop=True)
            others = df.drop([0, idx, idx+1] if idx+1 < len(df) else [0, idx]).copy().reset_index(drop=True)
            res[place] = [my, others]
    return res

def data_integration(pdf_dic, time_dic):
    integrated = {}
    for pk, pv in pdf_dic.items():
        match = next((k for k in time_dic.keys() if normalize_text(pk) in normalize_text(k)), None)
        if match: integrated[match] = pv + [time_dic[match]]
    return integrated, []

def process_full_month(integrated_dic, year, month):
    rows = []
    num_days = calendar.monthrange(year, month)[1]
    for d in range(1, num_days + 1):
        dt = f"{year}-{month:02d}-{d:02d}"
        col = d + 1
        for pk, (my, others, ts) in integrated_dic.items():
            if col >= my.shape[1]: continue
            val = str(my.iloc[0, col])
            if not val or val.strip() == "" or val.lower() == 'nan': continue
            for item in re.split(r'[,、\s\n]+', val):
                if not item.strip(): continue
                rows.append([f"{pk}_{item}", dt, "", dt, "", "True", "", pk])
                my_ts = ts[ts.iloc[:, 1].astype(str).str.strip() == item.strip()]
                if not my_ts.empty:
                    p_v = ""
                    for tc in range(2, ts.shape[1]):
                        c_v = str(my_ts.iloc[0, tc])
                        if c_v != p_v and c_v != "" and c_v.lower() != 'nan':
                            rows.append([f"【{c_v}】", dt, str(ts.iloc[0, tc]), dt, "", "False", "", pk])
                        p_v = c_v
    return rows
