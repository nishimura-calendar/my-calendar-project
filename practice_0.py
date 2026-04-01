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

def format_to_hhmm(val):
    """6.25 などの数値を HH:MM 形式に変換"""
    try:
        if val == "" or str(val).lower() == "nan": return ""
        num = float(val)
        h = int(num)
        m = int(round((num - h) * 60))
        if m >= 60: h += 1; m = 0
        return f"{h:02d}:{m:02d}"
    except:
        return str(val).strip()

def get_time_from_mark(text):
    """
    丸文字(①-⑨)を解析して時間を返す。基本事項に基づき@は考慮せず
    丸文字に対応する時間を抽出（マッピングは現場運用に合わせて調整）
    """
    text = normalize_text(text)
    # 代表的なマッピング（例）
    mapping = {
        "1": ("09:00", "18:00"), "2": ("10:00", "19:00"),
        "3": ("11:00", "20:00"), "4": ("12:00", "21:00"),
        "5": ("13:00", "22:00")
    }
    m = re.search(r'([1-9①-⑨])', text)
    if m:
        char = m.group(1)
        # 丸数字を数字に置換
        val = char.translate(str.maketrans("①②③④⑤⑥⑦⑧⑨", "123456789"))
        if val in mapping:
            return mapping[val][0], mapping[val][1], True
    return "", "", False

def read_excel_schedule(file_stream):
    """
    基本事項：A列=勤務地をkeyとして辞書に登録
    D列目以降の時間行(6.25等)をHH:MMに変換して保持
    """
    try:
        full_df = pd.read_excel(file_stream, header=None).fillna('')
        location_data_dic = {}
        
        # A列(index 0)に値がある行を場所の開始点とする
        loc_idx = full_df[full_df.iloc[:, 0].astype(str).str.strip() != ""].index.tolist()

        for i, start_row in enumerate(loc_idx):
            raw_name = str(full_df.iloc[start_row, 0]).strip()
            norm_name = normalize_text(raw_name)
            if not norm_name: continue
            
            end_row = loc_idx[i+1] if i+1 < len(loc_idx) else len(full_df)
            df_block = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
            
            # 1行目の時間ラベル(D列以降=index 3以降)をHH:MMに変換
            for col in range(3, df_block.shape[1]):
                df_block.iloc[0, col] = format_to_hhmm(df_block.iloc[0, col])
                
            location_data_dic[norm_name] = df_block
        return location_data_dic
    except Exception as e:
        print(f"Excel Error: {e}")
        return None

def pdf_reader(pdf_stream, target_staff):
    """
    勤務表PDFから特定個人の2行を抽出
    iloc(0,0)を勤務地として取得
    """
    table_dictionary = {}
    clean_target = normalize_text(target_staff)
    with pdfplumber.open(pdf_stream) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                df = pd.DataFrame(table)
                if df.empty or df.shape[1] < 2: continue
                
                # iloc(0,0)に勤務地の表記がある
                work_place = normalize_text(str(df.iloc[0, 0]))
                
                matched_indices = df.index[df.apply(lambda r: clean_target in normalize_text("".join(r.astype(str))), axis=1)].tolist()
                
                if matched_indices:
                    idx = matched_indices[0]
                    # 自分(my_daily_shift)の2行
                    my_daily_shift = df.iloc[idx : idx+2].reset_index(drop=True)
                    # 他人(other_daily_shift)
                    other_daily_shift = df[(df.index != idx) & (df.index != idx+1) & (df.index != 0)].reset_index(drop=True)
                    
                    table_dictionary[work_place] = [my_daily_shift, other_daily_shift]
    return table_dictionary
