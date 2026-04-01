import pandas as pd
import pdfplumber
import re
import io
import unicodedata
from googleapiclient.discovery import build

# --- 1. 時間整形関数 ---
def format_to_hhmm(val):
    try:
        if val == "" or str(val).lower() == "nan": 
            return ""
        if isinstance(val, (int, float)):
            num = float(val)
            h = int(num * 24 if num < 1 else num)
            m = int(round((num * 24 - h) * 60 if num < 1 else (num - h) * 60))
            if m >= 60: h += 1; m = 0
            return f"{h:02d}:{m:02d}"
        return str(val).strip()
    except:
        return str(val).strip()

# --- 2. 文字列正規化 ---
def normalize_text(text):
    if text is None or str(text).lower() == 'nan': return ""
    normalized = unicodedata.normalize('NFKC', str(text))
    return normalized.strip()

# --- 3. Google Drive / Sheets からの時程表取得 ---
def time_schedule_from_drive(service, spreadsheet_id):
    """
    Google Sheetsから時程表を取得し、勤務地をキーとした辞書を返す。
    A列=勤務地, B列=巡回区域, C列=ロッカ, D列以降=時間
    """
    try:
        range_name = 'Sheet1!A:Z' # シート名は適宜調整
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=range_name).execute()
        values = result.get('values', [])
        
        if not values:
            return {}

        full_df = pd.DataFrame(values).fillna('')
        location_data_dic = {}
        
        # A列が空でない行を勤務地の開始とする
        loc_idx = full_df[full_df.iloc[:, 0].astype(str).str.strip() != ""].index.tolist()
        
        for i, start_row in enumerate(loc_idx):
            raw_name = str(full_df.iloc[start_row, 0]).strip()
            norm_name = re.sub(r'\s+', '', unicodedata.normalize('NFKC', raw_name)).upper()
            if not norm_name: continue
            
            end_row = loc_idx[i+1] if i+1 < len(loc_idx) else len(full_df)
            df_block = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
            
            # 1行目の時間を整形
            for col in range(3, df_block.shape[1]):
                df_block.iloc[0, col] = format_to_hhmm(df_block.iloc[0, col])
                
            location_data_dic[norm_name] = df_block
            
        return location_data_dic
    except Exception as e:
        print(f"Google Sheets Read Error: {e}")
        return {}

# --- 4. PDF読み込み (打ち合わせ通りの勤務地判定) ---
def pdf_reader(pdf_stream, target_staff):
    table_dictionary = {}
    clean_target = re.sub(r'\s+', '', unicodedata.normalize('NFKC', target_staff))
    location_keywords = ["T1", "T2", "札幌", "羽田", "本町"]
    
    try:
        with pdfplumber.open(pdf_stream) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    if not table: continue
                    
                    processed_table = []
                    for row in table:
                        processed_row = [normalize_text(cell) for cell in row]
                        processed_table.append(processed_row)
                        
                    df = pd.DataFrame(processed_table).fillna('')
                    if df.empty or df.shape[1] < 2: continue
                    
                    # 勤務地の正確な読み込み (基本事項.docxのロジック参照)
                    # パンダス読み込み時に iloc(0,0) を勤務地として扱う
                    raw_val = str(df.iloc[0, 0])
                    lines = raw_val.split('\n')
                    target_index = raw_val.count('\n') // 2
                    work_place = lines[target_index] if target_index < len(lines) else (lines[-1] if lines else "UNKNOWN")
                    df.iloc[0, 0] = work_place
                    
                    norm_loc = re.sub(r'\s+', '', unicodedata.normalize('NFKC', work_place)).upper()
                    
                    col_0_search = [re.sub(r'\s+', '', str(val)) for val in df.iloc[:, 0].tolist()]
                    
                    if clean_target in col_0_search:
                        idx = col_0_search.index(clean_target)
                        # 自分のシフト (2行)
                        my_df = df.iloc[idx : idx+2].copy().reset_index(drop=True)
                        # 同僚のシフト
                        other_indices = [i for i in range(len(df)) if i not in [idx, idx+1]]
                        other_df = df.iloc[other_indices].copy().reset_index(drop=True)
                        
                        table_dictionary[norm_loc] = [my_df, other_df]
                        
    except Exception as e:
        print(f"PDF Reader Error: {e}")
    return table_dictionary

# --- 5. データ統合 ---
def data_integration(pdf_dic, time_dic):
    integrated_data = {}
    for loc_key, pdf_data in pdf_dic.items():
        matched_key = None
        for ex_key in time_dic.keys():
            if loc_key == ex_key or loc_key in ex_key or ex_key in loc_key:
                matched_key = ex_key
                break
        if matched_key:
            integrated_data[loc_key] = [pdf_data[0], pdf_data[1], time_dic[matched_key]]
    return integrated_data
