import pandas as pd
import pdfplumber
import re
import io
import unicodedata

def normalize_text(text):
    """全角半角、空白、改行を統一して比較しやすくする"""
    if not text or str(text).lower() == 'nan': return ""
    normalized = unicodedata.normalize('NFKC', str(text))
    return re.sub(r'[\s　\n\r]', '', normalized).strip()

def extract_year_month(pdf_stream):
    """PDFから年月を抽出"""
    try:
        with pdfplumber.open(pdf_stream) as pdf:
            text = pdf.pages[0].extract_text()
            if not text: return "2026", "3"
            m = re.search(r'(20\d{2})[年\.]\s*(\d{1,2})', text)
            if m: return m.group(1), m.group(2)
    except: pass
    return "2026", "3"

def parse_special_shift(text):
    """
    '10.5①19' や '10.5@19' 形式を解析。
    小数を時刻(HH:MM)に変換する。 (例: 10.25 -> 10:15)
    """
    text = normalize_text(text)
    # ① または @ で分割
    parts = re.split(r'[①@]', text)
    
    if len(parts) >= 2:
        try:
            def conv(v_str):
                num_match = re.search(r'(\d+\.?\d*)', v_str)
                if not num_match: return None
                v = float(num_match.group(1))
                h = int(v)
                m = int(round((v % 1) * 60))
                if m >= 60: h += 1; m = 0
                return f"{h:02d}:{m:02d}"
            
            start = conv(parts[0])
            end = conv(parts[1])
            if start and end:
                return start, end, True
        except: pass
    return "", "", False

def read_excel_schedule(file_stream):
    """
    アップロードされたエクセルファイルから時程表を読み込む。
    6.25 -> 06:15 などの変換を行う。
    """
    try:
        full_df = pd.read_excel(file_stream, header=None).fillna('')
        location_data_dic = {}
        
        # A列に文字がある行を場所の区切りとする
        loc_idx = full_df[full_df.iloc[:, 0].astype(str).str.strip() != ""].index.tolist()
        
        for i, start_row in enumerate(loc_idx):
            raw_name = str(full_df.iloc[start_row, 0])
            norm_name = normalize_text(raw_name)
            end_row = loc_idx[i+1] if i+1 < len(loc_idx) else len(full_df)
            df = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
            
            # 1行目の時刻ラベルを変換 (6.25 -> 06:15)
            for col in range(2, df.shape[1]):
                val = df.iloc[0, col]
                try:
                    num = float(val)
                    if 0 < num < 24.1:
                        h = int(num); m = int(round((num - h) * 60))
                        if m >= 60: h += 1; m = 0
                        df.iloc[0, col] = f"{h:02d}:{m:02d}"
                except: pass
            location_data_dic[norm_name] = df
        return location_data_dic
    except Exception as e:
        return None

def pdf_reader(pdf_stream, target_staff):
    """PDFから指定スタッフの勤務情報を2行分(記号・特記事項)抽出"""
    pdf_dic = {}
    clean_target = normalize_text(target_staff)
    with pdfplumber.open(pdf_stream) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                df = pd.DataFrame(table)
                if df.empty or df.shape[1] < 2: continue
                loc_name = str(df.iloc[0, 0]).replace('\n', '').strip()
                my_s = None
                for idx, row in df.iterrows():
                    row_str = "".join(row.astype(str))
                    if clean_target in normalize_text(row_str):
                        my_s = df.iloc[idx : idx+2, :].reset_index(drop=True)
                        break
                if my_s is not None:
                    pdf_dic[loc_name] = [my_s, df]
    return pdf_dic
