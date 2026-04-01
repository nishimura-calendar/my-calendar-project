import pandas as pd
import pdfplumber
import re
import io
import unicodedata
from googleapiclient.discovery import build

# --- 1. 時間整形関数 ---
def format_to_hhmm(val):
    if val is None or str(val).lower() == "nan" or str(val).strip() == "":
        return ""
    try:
        if isinstance(val, (int, float)):
            num = float(val)
            h = int(num * 24 if num < 1 else num)
            m = int(round((num * 24 - h) * 60 if num < 1 else (num - h) * 60))
            if m >= 60: h += 1; m = 0
            return f"{h:02d}:{m:02d}"
        
        s_val = str(val).strip()
        if ":" in s_val:
            parts = s_val.split(":")
            return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
        
        if s_val.replace('.', '').isdigit():
            num = float(s_val)
            if num < 1:
                return format_to_hhmm(num)
            return f"{int(num):02d}:00"
        return s_val
    except:
        return str(val).strip()

# --- 2. 文字列正規化 ---
def normalize_for_match(text):
    if text is None or str(text).lower() == 'nan': return ""
    normalized = unicodedata.normalize('NFKC', str(text))
    return re.sub(r'[\s　\n\r\t]', '', normalized).strip().upper()

# --- 3. Google Sheets からの時程表取得 ---
def time_schedule_from_drive(service, spreadsheet_id):
    try:
        spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheet_name = spreadsheet['sheets'][0]['properties']['title']
        
        range_name = f"'{sheet_name}'!A:Z" 
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=range_name).execute()
        values = result.get('values', [])
        
        if not values:
            return {}

        max_cols = max(len(row) for row in values)
        padded_values = [row + [''] * (max_cols - len(row)) for row in values]
        full_df = pd.DataFrame(padded_values).fillna('')
        
        location_data_dic = {}
        loc_idx = []
        for i in range(len(full_df)):
            cell_v = str(full_df.iloc[i, 0]).strip()
            if cell_v != "" and cell_v.lower() != "nan":
                loc_idx.append(i)
        
        for i, start_row in enumerate(loc_idx):
            raw_name = str(full_df.iloc[start_row, 0]).strip()
            # キーは「正規化後の文字列」
            match_key = normalize_for_match(raw_name)
            if not match_key: continue
            
            end_row = loc_idx[i+1] if i+1 < len(loc_idx) else len(full_df)
            df_block = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
            
            for col in range(3, df_block.shape[1]):
                df_block.iloc[0, col] = format_to_hhmm(df_block.iloc[0, col])
                
            location_data_dic[match_key] = {
                "raw_name": raw_name,
                "df": df_block
            }
        return location_data_dic
    except Exception as e:
        print(f"Google Sheets Error: {e}")
        return {}

# --- 4. PDF読み取り ---
def pdf_reader(pdf_stream, target_staff):
    table_dictionary = {}
    clean_target = normalize_for_match(target_staff)
    
    try:
        with pdfplumber.open(pdf_stream) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    if not table: continue
                    df = pd.DataFrame(table).fillna('')
                    if df.empty or df.shape[1] < 2: continue
                    
                    # 勤務地セルの生データ取得
                    raw_loc_cell = str(df.iloc[0, 0])
                    loc_lines = [l.strip() for l in raw_loc_cell.split('\n') if l.strip()]
                    detected_loc_name = loc_lines[len(loc_lines)//2] if loc_lines else "抽出失敗"
                    
                    match_loc_key = normalize_for_match(detected_loc_name)

                    col_0_norm = [normalize_for_match(str(val)) for val in df.iloc[:, 0].tolist()]
                    
                    if clean_target in col_0_norm:
                        idx = col_0_norm.index(clean_target)
                        my_df = df.iloc[idx : idx+2].copy().reset_index(drop=True)
                        
                        for r in range(len(my_df)):
                            for c in range(len(my_df.columns)):
                                val = str(my_df.iloc[r, c])
                                if '\n' in val:
                                    my_df.iloc[r, c] = val.replace('\n', ' / ')
                        
                        other_indices = [i for i in range(len(df)) if i not in [idx, idx+1]]
                        other_df = df.iloc[other_indices].copy().reset_index(drop=True)
                        
                        table_dictionary[match_loc_key] = {
                            "raw_name": detected_loc_name,
                            "my_df": my_df,
                            "other_df": other_df
                        }
    except Exception as e:
        print(f"PDF Error: {e}")
    return table_dictionary

# --- 5. 統合 (今回はデバッグ用にそのまま返す) ---
def data_integration(pdf_dic, time_dic):
    # 紐付けが成功したものだけを返す（後ほどapp.py側で未紐付けも表示）
    integrated_data = {}
    for pdf_key, pdf_content in pdf_dic.items():
        if pdf_key in time_dic:
            integrated_data[pdf_key] = [
                pdf_content["my_df"],
                pdf_content["other_df"],
                time_dic[pdf_key]["df"]
            ]
    return integrated_data
