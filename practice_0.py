import pandas as pd
import pdfplumber
import re
import io
import unicodedata
from googleapiclient.discovery import build

# --- 1. 時間整形関数 (6.25 などの数値に対応) ---
def format_to_hhmm(val):
    if val is None or str(val).lower() == "nan" or str(val).strip() == "":
        return ""
    try:
        # 数値（フロート）の場合: 6.25 -> 06:15
        if isinstance(val, (int, float)) or (isinstance(val, str) and val.replace('.', '').isdigit()):
            num = float(val)
            if 0 < num < 1:  # シリアル値の場合
                h = int(num * 24)
                m = int(round((num * 24 - h) * 60))
            else:  # 6.25 などの時間数の場合
                h = int(num)
                m = int(round((num - h) * 60))
            
            if m >= 60: h += 1; m = 0
            return f"{h:02d}:{m:02d}"
        
        # すでに 09:00 などの形式の場合
        s_val = str(val).strip()
        if ":" in s_val:
            parts = s_val.split(":")
            return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
            
        return s_val
    except:
        return str(val).strip()

# --- 2. 文字列正規化 ---
def normalize_for_match(text):
    if text is None or str(text).lower() == 'nan': return ""
    normalized = unicodedata.normalize('NFKC', str(text))
    return re.sub(r'[\s　\n\r\t]', '', normalized).strip().upper()

# --- 3. Google Sheets からの時程表取得 (抽出強化版) ---
def time_schedule_from_drive(service, spreadsheet_id):
    try:
        spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheet_name = spreadsheet['sheets'][0]['properties']['title']
        
        range_name = f"'{sheet_name}'!A1:Z500" 
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=range_name).execute()
        values = result.get('values', [])
        
        if not values:
            return {}

        # DataFrame化
        max_cols = max(len(row) for row in values)
        padded_values = [row + [''] * (max_cols - len(row)) for row in values]
        full_df = pd.DataFrame(padded_values).fillna('')
        
        location_data_dic = {}
        # A列に勤務地名が入っている行を特定
        loc_idx = []
        for i in range(len(full_df)):
            cell_v = str(full_df.iloc[i, 0]).strip()
            # 勤務地名（T1, T2など）を想定。ヘッダーや空文字は除外。
            if cell_v != "" and cell_v.lower() != "nan" and cell_v not in ["出勤", "退勤", "実働時間"]:
                loc_idx.append(i)
        
        for i, start_row in enumerate(loc_idx):
            raw_name = str(full_df.iloc[start_row, 0]).strip()
            match_key = normalize_for_match(raw_name)
            
            # 次の勤務地までの範囲を切り出し
            end_row = loc_idx[i+1] if i+1 < len(loc_idx) else len(full_df)
            df_block = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
            
            # 時間ヘッダー（1行目）の整形
            # 今回のCSV構造では4列目(index 3)から時間が始まっている
            for col in range(1, df_block.shape[1]):
                val = df_block.iloc[0, col]
                if val != "":
                    df_block.iloc[0, col] = format_to_hhmm(val)
                
            location_data_dic[match_key] = {
                "raw_name": raw_name,
                "df": df_block
            }
            
        return location_data_dic
    except Exception as e:
        print(f"Sheet Error: {e}")
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
                    
                    # 勤務地情報の取得
                    raw_loc_cell = str(df.iloc[0, 0])
                    loc_lines = [l.strip() for l in raw_loc_cell.split('\n') if l.strip()]
                    detected_loc = loc_lines[len(loc_lines)//2] if loc_lines else raw_loc_cell
                    match_key = normalize_for_match(detected_loc)

                    col_0_norm = [normalize_for_match(str(val)) for val in df.iloc[:, 0].tolist()]
                    
                    if clean_target in col_0_norm:
                        idx = col_0_norm.index(clean_target)
                        my_df = df.iloc[idx : idx+2].copy().reset_index(drop=True)
                        
                        # 改行処理
                        for r in range(len(my_df)):
                            for c in range(len(my_df.columns)):
                                val = str(my_df.iloc[r, c])
                                if '\n' in val:
                                    my_df.iloc[r, c] = val.replace('\n', ' / ')
                        
                        other_indices = [i for i in range(len(df)) if i not in [idx, idx+1]]
                        table_dictionary[match_key] = {
                            "raw_name": detected_loc,
                            "my_df": my_df,
                            "other_df": df.iloc[other_indices].copy()
                        }
    except Exception as e:
        print(f"PDF Error: {e}")
    return table_dictionary

# --- 5. 統合 (今回は確認用にパス) ---
def data_integration(pdf_dic, time_dic):
    integrated = {}
    for k, v in pdf_dic.items():
        if k in time_dic:
            integrated[k] = [v["my_df"], v["other_df"], time_dic[k]["df"]]
    return integrated
