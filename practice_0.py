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
        # 数値（フロートまたは数値形式の文字列）の場合
        s_val = str(val).strip()
        if s_val.replace('.', '').isdigit():
            num = float(s_val)
            if 0 < num < 1:  # シリアル値 (0.375など)
                h = int(num * 24)
                m = int(round((num * 24 - h) * 60))
            elif num >= 1:   # 6.25 などの時間数
                h = int(num)
                m = int(round((num - h) * 60))
            else:
                return s_val
            
            if m >= 60: h += 1; m = 0
            return f"{h:02d}:{m:02d}"
        
        # すでに 09:00 などの形式の場合
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
    # 空白・改行を完全に除去して大文字化
    return re.sub(r'[\s　\n\r\t]', '', normalized).strip().upper()

# --- 3. Google Sheets からの時程表取得 (超安定版) ---
def time_schedule_from_drive(service, spreadsheet_id):
    try:
        # シート名取得
        spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheet_name = spreadsheet['sheets'][0]['properties']['title']
        
        # A1から広範囲に取得
        range_name = f"'{sheet_name}'!A1:Z500" 
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=range_name).execute()
        values = result.get('values', [])
        
        if not values:
            return {}

        # 1. すべての行の長さを最大値に揃える (APIは空の末尾列を省略するため)
        max_cols = max(len(row) for row in values)
        data = [row + [''] * (max_cols - len(row)) for row in values]
        full_df = pd.DataFrame(data).fillna('')
        
        location_data_dic = {}
        
        # 2. A列をスキャンして勤務地(T1, T2等)の開始行を特定
        # CSVの構造上、1行目からT1が始まっている可能性があるため、全行チェック
        loc_indices = []
        for i in range(len(full_df)):
            cell_v = str(full_df.iloc[i, 0]).strip()
            # 勤務地名として判定する条件: 空でない、かつ「出勤」等のキーワードでない
            if cell_v != "" and cell_v.lower() != "nan":
                if cell_v not in ["出勤", "退勤", "実働時間", "休憩時間", "巡回区域", "ロッカ"]:
                    # 文字数が多すぎる場合はメモ書きと判断して除外
                    if len(cell_v) < 15:
                        loc_indices.append(i)
        
        if not loc_indices:
            return {}

        # 3. 各勤務地ブロックを切り出す
        for i, start_row in enumerate(loc_indices):
            raw_name = str(full_df.iloc[start_row, 0]).strip()
            match_key = normalize_for_match(raw_name)
            
            if not match_key: continue
            
            # 次の勤務地行、または最終行までを範囲とする
            end_row = loc_indices[i+1] if i+1 < len(loc_indices) else len(full_df)
            df_block = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
            
            # 4. 1行目(時間ヘッダー)を整形
            # D列目(index 3)以降に 6.25 等が入っていることが多いため、全列確認して整形
            for col in range(1, df_block.shape[1]):
                val = str(df_block.iloc[0, col])
                if val != "":
                    df_block.iloc[0, col] = format_to_hhmm(val)
                
            location_data_dic[match_key] = {
                "raw_name": raw_name,
                "df": df_block
            }
            
        return location_data_dic
    except Exception as e:
        print(f"Spreadsheet access error: {e}")
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
                    
                    # 勤務地セルの特定 (1行1列目)
                    raw_loc_cell = str(df.iloc[0, 0])
                    loc_lines = [l.strip() for l in raw_loc_cell.split('\n') if l.strip()]
                    detected_loc = loc_lines[len(loc_lines)//2] if loc_lines else raw_loc_cell
                    match_key = normalize_for_match(detected_loc)

                    # 氏名列を正規化して検索
                    col_0_norm = [normalize_for_match(str(val)) for val in df.iloc[:, 0].tolist()]
                    
                    if clean_target in col_0_norm:
                        idx = col_0_norm.index(clean_target)
                        # 自分の2行(名前行と記号行)を取得
                        my_df = df.iloc[idx : idx+2].copy().reset_index(drop=True)
                        
                        # 改行を / に置換
                        for r in range(len(my_df)):
                            for c in range(len(my_df.columns)):
                                val = str(my_df.iloc[r, c])
                                if '\n' in val:
                                    my_df.iloc[r, c] = val.replace('\n', ' / ')
                        
                        # 同僚のシフト (自分以外)
                        other_indices = [i for i in range(len(df)) if i not in [idx, idx+1]]
                        other_df = df.iloc[other_indices].copy().reset_index(drop=True)
                        
                        table_dictionary[match_key] = {
                            "raw_name": detected_loc,
                            "my_df": my_df,
                            "other_df": other_df
                        }
    except Exception as e:
        print(f"PDF Analysis Error: {e}")
    return table_dictionary

# --- 5. 統合ロジック ---
def data_integration(pdf_dic, time_dic):
    integrated = {}
    for k, v in pdf_dic.items():
        # キーが完全一致、または一方がもう一方を含む場合も救済
        matched_key = None
        if k in time_dic:
            matched_key = k
        else:
            for tk in time_dic.keys():
                if k in tk or tk in k:
                    matched_key = tk
                    break
        
        if matched_key:
            integrated[v["raw_name"]] = [
                v["my_df"],
                v["other_df"],
                time_dic[matched_key]["df"]
            ]
    return integrated
