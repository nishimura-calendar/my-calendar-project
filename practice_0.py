import pandas as pd
import pdfplumber
import re
import io
import unicodedata

# --- 0. 名称変換設定 (PDFの表記をExcelのA列に合わせる) ---
# PDFで抽出される可能性のある名前を、Excelで管理している名前に変換します。
LOCATION_MAP = {
    "第1ターミナル": "T1",
    "第2ターミナル": "T2",
    "関西国際空港第1": "T1",
    "関西国際空港第2": "T2",
    # 札幌や羽田なども、PDF側の表記が特殊ならここに追加します
    # "新千歳空港": "札幌", 
}

# --- 1. 時間整形関数 ---
def format_to_hhmm(val):
    try:
        if val == "" or str(val).lower() == "nan": 
            return ""
        num = float(val)
        h = int(num * 24 if num < 1 else num)
        m = int(round((num * 24 - h) * 60 if num < 1 else (num - h) * 60))
        if m >= 60: h += 1; m = 0
        return f"{h:02d}:{m:02d}"
    except:
        return str(val).strip()

# --- 2. 文字列正規化 ---
def normalize_text(text):
    if text is None or str(text).lower() == 'nan': return ""
    normalized = unicodedata.normalize('NFKC', str(text))
    # 空白や改行を削除し、大文字に統一
    return re.sub(r'[\s　\n\r]', '', normalized).strip().upper()

# --- 3. 勤務地名の変換ロジック ---
def map_location_name(raw_name):
    """
    PDFから抽出された生の名称を、Excel側の名称に変換します。
    """
    norm_name = normalize_text(raw_name)
    # マップにあるキーワードが含まれているかチェック
    for key, excel_name in LOCATION_MAP.items():
        if normalize_text(key) in norm_name:
            return normalize_text(excel_name)
    return norm_name

# --- 4. 時程表（Excel）の読み込み ---
def read_excel_schedule(file_stream):
    try:
        full_df = pd.read_excel(file_stream, header=None).fillna('')
        location_data_dic = {}
        loc_idx = full_df[full_df.iloc[:, 0].astype(str).str.strip() != ""].index.tolist()
        
        for i, start_row in enumerate(loc_idx):
            raw_name = str(full_df.iloc[start_row, 0]).strip()
            norm_name = normalize_text(raw_name) # Excel側の名前も正規化
            if not norm_name: continue
            
            end_row = loc_idx[i+1] if i+1 < len(loc_idx) else len(full_df)
            df_block = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
            
            for col in range(3, df_block.shape[1]):
                df_block.iloc[0, col] = format_to_hhmm(df_block.iloc[0, col])
                
            location_data_dic[norm_name] = df_block
        return location_data_dic
    except:
        return None

# --- 5. PDF読み込み関数 ---
def pdf_reader(pdf_stream, target_staff):
    table_dictionary = {}
    clean_target = normalize_text(target_staff)
    
    try:
        with pdfplumber.open(pdf_stream) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                
                # 勤務地特定 (中央値付近)
                target_index = len(lines) // 2
                raw_place = lines[target_index] if lines else "unknown"
                
                # 重要：ここで名称を Excel 形式 (T1, T2 など) に変換
                work_place = map_location_name(raw_place)
                
                tables = page.extract_tables()
                for table in tables:
                    if not table: continue
                    df = pd.DataFrame(table).fillna('')
                    if df.empty or df.shape[1] < 2: continue
                    
                    df.iloc[0, 0] = work_place
                    names_list = [normalize_text(str(val)) for val in df.iloc[:, 0].tolist()]
                    
                    if clean_target in names_list:
                        idx = names_list.index(clean_target)
                        my_daily_shift = df.iloc[idx : idx+2].copy().reset_index(drop=True)
                        other_indices = [i for i in range(len(df)) if i not in [0, idx, idx+1]]
                        other_daily_shift = df.iloc[other_indices].copy().reset_index(drop=True)
                        table_dictionary[work_place] = [my_daily_shift, other_daily_shift]
                        
    except Exception as e:
        print(f"PDF Reader Error: {e}")
    return table_dictionary

# --- 6. データ統合関数 ---
def data_integration(pdf_dic, time_schedule_dic):
    integrated_data = {}
    for loc_key, pdf_data in pdf_dic.items():
        # 両方のキーが正規化されているため、一致しやすくなります
        if loc_key in time_schedule_dic:
            integrated_data[loc_key] = [pdf_data[0], pdf_data[1], time_schedule_dic[loc_key]]
    return integrated_data
