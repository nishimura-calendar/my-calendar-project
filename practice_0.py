import pandas as pd
import pdfplumber
import re
import io
import unicodedata

# --- 1. 時間整形関数 (6.25 などの数値に対応) ---
def format_to_hhmm(val):
    if val is None or str(val).lower() == "nan" or str(val).strip() == "":
        return ""
    try:
        s_val = str(val).strip()
        if s_val.replace('.', '').isdigit():
            num = float(s_val)
            if 0 < num < 1:  # シリアル値
                h = int(num * 24)
                m = int(round((num * 24 - h) * 60))
            else:  # 6.25 などの数値
                h = int(num)
                m = int(round((num - h) * 60))
            if m >= 60: h += 1; m = 0
            return f"{h:02d}:{m:02d}"
        if ":" in s_val:
            parts = s_val.split(":")
            return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
        return s_val
    except:
        return str(val).strip()

# --- 2. 文字列正規化 ---
def normalize_for_match(text):
    if text is None or str(text).lower() == 'nan': return ""
    # 全角半角の統一、空白・記号の除去
    normalized = unicodedata.normalize('NFKC', str(text))
    return re.sub(r'[^a-zA-Z0-9ぁ-んァ-ヶ亜-熙]', '', normalized).strip().upper()

# --- 3. Google Sheets からの取得 (全自動探索強化版) ---
def time_schedule_from_drive(service, spreadsheet_id):
    try:
        spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheet_name = spreadsheet['sheets'][0]['properties']['title']
        
        # A1:Z500 の範囲をすべて取得
        range_name = f"'{sheet_name}'!A1:Z500" 
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=range_name).execute()
        values = result.get('values', [])
        
        if not values:
            return {}

        # DataFrame化 (APIが省略した空列を補完)
        max_cols = max(len(row) for row in values)
        data = [row + [''] * (max_cols - len(row)) for row in values]
        full_df = pd.DataFrame(data).fillna('')
        
        location_data_dic = {}
        loc_indices = []

        # 全セルをスキャンして「T1」「T2」などを探す
        # A列だけでなく、横にずれている可能性も考慮
        for r_idx in range(len(full_df)):
            for c_idx in range(min(5, full_df.shape[1])): # 最初の5列をチェック
                cell_val = str(full_df.iloc[r_idx, c_idx]).strip()
                norm_val = normalize_for_match(cell_val)
                
                # 「T1」「T2」などの特定のキーワードで始まる行を記録
                if norm_val in ["T1", "T2", "T3", "T4"] or any(k in cell_val for k in ["札幌", "羽田", "成田", "本町"]):
                    loc_indices.append((r_idx, c_idx, cell_val))
                    break # その行で1つ見つかれば十分

        for i, (start_row, key_col, raw_name) in enumerate(loc_indices):
            match_key = normalize_for_match(raw_name)
            
            # 次の勤務地行、または最終行までを切り出し
            end_row = loc_indices[i+1][0] if i+1 < len(loc_indices) else len(full_df)
            df_block = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
            
            # 1行目(時間ヘッダー)を整形
            for col in range(df_block.shape[1]):
                val = df_block.iloc[0, col]
                if val != "" and col != key_col:
                    df_block.iloc[0, col] = format_to_hhmm(val)
            
            location_data_dic[match_key] = {
                "raw_name": raw_name,
                "df": df_block
            }
        return location_data_dic
    except Exception as e:
        # エラーが発生した場合は空の辞書を返す
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
                    if not table or len(table) < 2: continue
                    df = pd.DataFrame(table).fillna('')
                    
                    # 勤務地セルの特定 (1行1列目)
                    raw_loc_cell = str(df.iloc[0, 0])
                    loc_lines = [l.strip() for l in raw_loc_cell.split('\n') if l.strip()]
                    # 改行がある場合は真ん中の行、なければそのまま
                    detected_loc = loc_lines[len(loc_lines)//2] if loc_lines else raw_loc_cell
                    match_key = normalize_for_match(detected_loc)

                    # 氏名列を検索
                    col_0_norm = [normalize_for_match(str(val)) for val in df.iloc[:, 0].tolist()]
                    
                    if clean_target in col_0_norm:
                        idx = col_0_norm.index(clean_target)
                        my_df = df.iloc[idx : idx+2].copy().reset_index(drop=True)
                        
                        # セル内の改行処理
                        for r in range(len(my_df)):
                            for c in range(len(my_df.columns)):
                                val = str(my_df.iloc[r, c])
                                if '\n' in val:
                                    my_df.iloc[r, c] = val.replace('\n', ' / ')
                        
                        # 同僚の情報を抽出
                        other_df = df.iloc[[i for i in range(len(df)) if i not in [idx, idx+1]]].copy()
                        
                        table_dictionary[match_key] = {
                            "raw_name": detected_loc,
                            "my_df": my_df,
                            "other_df": other_df
                        }
    except Exception as e:
        print(f"PDF Error: {e}")
    return table_dictionary

# --- 5. 統合 ---
def data_integration(pdf_dic, time_dic):
    integrated = {}
    for k, v in pdf_dic.items():
        matched_key = None
        if k in time_dic:
            matched_key = k
        else:
            # 曖昧一致 (T2 と T2(羽田) など)
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
