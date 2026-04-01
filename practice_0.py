import pandas as pd
import pdfplumber
import re
import io
import unicodedata

# --- 1. 時間整形関数 (基本事項にある 6.25 などの数値に対応) ---
def format_to_hhmm(val):
    if val is None or str(val).lower() == "nan" or str(val).strip() == "":
        return ""
    try:
        s_val = str(val).strip()
        # 6.25 などの数値やシリアル値の判定
        if s_val.replace('.', '').isdigit():
            num = float(s_val)
            if 0 < num < 1:  # Excelシリアル値
                h = int(num * 24)
                m = int(round((num * 24 - h) * 60))
            else:  # 6.25 などの時間数
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
    normalized = unicodedata.normalize('NFKC', str(text))
    return re.sub(r'[^a-zA-Z0-9ぁ-んァ-ヶ亜-熙]', '', normalized).strip().upper()

# --- 3. エクセルから時程表データを抽出 (基本事項の定義に準拠) ---
def extract_time_schedule_from_excel(excel_file):
    try:
        # Excel読み込み
        df_all = pd.read_excel(excel_file, header=None).fillna('')
        
        location_data_dic = {}
        loc_indices = []

        # 全行スキャン
        for r in range(len(df_all)):
            # 基本事項：A列=勤務地、B,C列は空白
            a_val = str(df_all.iloc[r, 0]).strip()
            b_val = str(df_all.iloc[r, 1]).strip()
            c_val = str(df_all.iloc[r, 2]).strip()
            
            if a_val != "" and b_val == "" and c_val == "":
                # 勤務地行と判定
                loc_indices.append((r, a_val))

        for i, (start_row, raw_name) in enumerate(loc_indices):
            match_key = normalize_for_match(raw_name)
            
            # 次の勤務地行、または最終行までを取得
            end_row = loc_indices[i+1][0] if i+1 < len(loc_indices) else len(df_all)
            df_block = df_all.iloc[start_row:end_row, :].copy().reset_index(drop=True)
            
            # 1行目(時間行)：基本事項に基づきD列目(index=3)以降を整形
            for col in range(3, df_block.shape[1]):
                val = df_block.iloc[0, col]
                if val != "":
                    df_block.iloc[0, col] = format_to_hhmm(val)
            
            location_data_dic[match_key] = {
                "raw_name": raw_name,
                "df": df_block
            }
        return location_data_dic
    except Exception as e:
        print(f"Excel Error: {e}")
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
                    
                    # 勤務地セルの特定 (iloc(0,0))
                    raw_loc_cell = str(df.iloc[0, 0])
                    loc_lines = [l.strip() for l in raw_loc_cell.split('\n') if l.strip()]
                    detected_loc = loc_lines[len(loc_lines)//2] if loc_lines else raw_loc_cell
                    match_key = normalize_for_match(detected_loc)

                    col_0_norm = [normalize_for_match(str(val)) for val in df.iloc[:, 0].tolist()]
                    
                    if clean_target in col_0_norm:
                        idx = col_0_norm.index(clean_target)
                        my_df = df.iloc[idx : idx+2].copy().reset_index(drop=True)
                        for r in range(len(my_df)):
                            for c in range(len(my_df.columns)):
                                val = str(my_df.iloc[r, c])
                                if '\n' in val:
                                    my_df.iloc[r, c] = val.replace('\n', ' / ')
                        
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
            for tk in time_dic.keys():
                if k in tk or tk in k:
                    matched_key = tk
                    break
        if matched_key:
            integrated[v["raw_name"]] = [v["my_df"], v["other_df"], time_dic[matched_key]["df"]]
    return integrated
