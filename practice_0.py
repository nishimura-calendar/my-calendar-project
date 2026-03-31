import pandas as pd
import pdfplumber
import re
import unicodedata

def normalize_text(text):
    """全角半角、空白、改行を統一"""
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

def get_time_from_mark(text):
    """
    '①' などの丸文字から時間を抽出する。
    ここでは例として ①=9:00-18:00 のような変換ロジックを想定。
    必要に応じて詳細なマッピングを追加してください。
    """
    text = normalize_text(text)
    # デフォルトのダミー設定（実際のマッピングに合わせて修正可能）
    mapping = {
        "1": ("09:00", "18:00"),
        "2": ("10:00", "19:00"),
        "3": ("11:00", "20:00"),
        "4": ("12:00", "21:00"),
        "5": ("13:00", "22:00"),
    }
    # 丸数字や数字を探す
    m = re.search(r'([1-9①-⑨])', text)
    if m:
        val = m.group(1).replace('①','1').replace('②','2').replace('③','3').replace('④','4').replace('⑤','5')
        if val in mapping:
            return mapping[val][0], mapping[val][1], True
    return "", "", False

def read_excel_schedule(file_stream):
    """A列をキーとした場所ごとの辞書を作成"""
    try:
        full_df = pd.read_excel(file_stream, header=None).fillna('')
        location_data_dic = {}
        loc_idx = full_df[full_df.iloc[:, 0].astype(str).str.strip() != ""].index.tolist()

        for i, start_row in enumerate(loc_idx):
            raw_name = str(full_df.iloc[start_row, 0]).strip()
            norm_name = normalize_text(raw_name)
            if not norm_name: continue
            
            end_row = loc_idx[i+1] if i+1 < len(loc_idx) else len(full_df)
            df_block = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
            
            # 1行目の数値時刻変換
            for col in range(2, df_block.shape[1]):
                val = df_block.iloc[0, col]
                try:
                    num = float(val)
                    if 0 < num < 24.1:
                        h = int(num); m = int(round((num - h) * 60))
                        if m >= 60: h += 1; m = 0
                        df_block.iloc[0, col] = f"{h:02d}:{m:02d}"
                except: pass
            location_data_dic[norm_name] = df_block
        return location_data_dic
    except: return None

def pdf_reader(pdf_stream, target_staff):
    """PDFから特定個人の2行（記号行・特記行）を抽出"""
    pdf_dic = {}
    clean_target = normalize_text(target_staff)
    with pdfplumber.open(pdf_stream) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                df = pd.DataFrame(table)
                if df.empty or df.shape[1] < 2: continue
                raw_loc = normalize_text(str(df.iloc[0, 0]))
                my_rows = None
                for idx, row in df.iterrows():
                    if clean_target in normalize_text("".join(row.astype(str))):
                        my_rows = df.iloc[idx : idx+2, :].reset_index(drop=True)
                        break
                if my_rows is not None:
                    pdf_dic[raw_loc] = my_rows
    return pdf_dic
