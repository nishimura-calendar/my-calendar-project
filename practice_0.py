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
    """'10.5①19' などの丸文字・特殊時間を解析"""
    text = normalize_text(text)
    parts = re.split(r'[①@]', text)
    if len(parts) >= 2:
        try:
            def conv(v_str):
                num_match = re.search(r'(\d+\.?\d*)', v_str)
                if not num_match: return None
                v = float(num_match.group(1))
                h = int(v); m = int(round((v % 1) * 60))
                if m >= 60: h += 1; m = 0
                return f"{h:02d}:{m:02d}"
            start = conv(parts[0]); end = conv(parts[1])
            if start and end: return start, end, True
        except: pass
    return "", "", False

def read_excel_schedule(file_stream):
    """
    時程表エクセルを解析。
    A列に値がある行を「場所(Key)」として認識し、辞書に登録する。
    1行目の数値(6.25等)を時刻形式(06:15等)に事前変換する。
    """
    try:
        full_df = pd.read_excel(file_stream, header=None).fillna('')
        location_data_dic = {}
        
        # A列(index 0)に値がある行のインデックスを特定（場所の区切り）
        loc_idx = full_df[full_df.iloc[:, 0].astype(str).str.strip() != ""].index.tolist()

        for i, start_row in enumerate(loc_idx):
            # A列の値を場所名(Key)として取得
            raw_name = str(full_df.iloc[start_row, 0]).strip()
            norm_name = normalize_text(raw_name)
            if not norm_name: continue
            
            # 次の場所の開始行、またはシート末尾までを範囲とする
            end_row = loc_idx[i+1] if i+1 < len(loc_idx) else len(full_df)
            df_block = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
            
            # --- 重要: 1行目の数値時刻(6.25等)をHH:MMに変換 ---
            for col in range(2, df_block.shape[1]):
                val = df_block.iloc[0, col]
                try:
                    num = float(val)
                    if 0 < num < 24.1:
                        h = int(num); m = int(round((num - h) * 60))
                        if m >= 60: h += 1; m = 0
                        df_block.iloc[0, col] = f"{h:02d}:{m:02d}"
                except: pass
            
            # 辞書に場所名をキーとして、その下の時程表データを保存
            location_data_dic[norm_name] = df_block
            
        return location_data_dic
    except Exception as e:
        print(f"Excel Error: {e}")
        return None

def pdf_reader(pdf_stream, target_staff):
    """PDFから指定スタッフの勤務情報を抽出"""
    pdf_dic = {}
    clean_target = normalize_text(target_staff)
    with pdfplumber.open(pdf_stream) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                df = pd.DataFrame(table)
                if df.empty or df.shape[1] < 2: continue
                
                # PDF上の場所名を取得 (通常は表の左上)
                raw_loc = str(df.iloc[0, 0]).replace('\n', '').strip()
                norm_loc = normalize_text(raw_loc)
                
                my_rows = None
                for idx, row in df.iterrows():
                    # 行全体から名前を検索
                    row_str = "".join(row.astype(str))
                    if clean_target in normalize_text(row_str):
                        # 名前のある行(記号)と下の行(特記)を取得
                        my_rows = df.iloc[idx : idx+2, :].reset_index(drop=True)
                        break
                if my_rows is not None:
                    pdf_dic[norm_loc] = my_rows
    return pdf_dic
