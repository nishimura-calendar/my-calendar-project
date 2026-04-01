import pandas as pd
import pdfplumber
import re
import io
import unicodedata

# --- 1. 時間整形関数 (Excelの時間表示対応) ---
def format_to_hhmm(val):
    try:
        if val == "" or str(val).lower() == "nan": 
            return ""
        
        # 数値(シリアル値含む)の場合
        if isinstance(val, (int, float)):
            num = float(val)
            # 1未満は24時間換算(シリアル値)、それ以上はそのままの時間数
            h = int(num * 24 if num < 1 else num)
            m = int(round((num * 24 - h) * 60 if num < 1 else (num - h) * 60))
            if m >= 60: h += 1; m = 0
            return f"{h:02d}:{m:02d}"
        
        # 文字列の場合、不要な空白や改行を整理
        s_val = str(val).strip().replace('\n', ' ')
        # すでに HH:MM 形式ならそのまま、そうでなければ整形を試みる
        return s_val
    except:
        return str(val).strip()

# --- 2. 文字列正規化 ---
def normalize_text(text):
    if text is None or str(text).lower() == 'nan': return ""
    # Unicode正規化 (全角半角、記号の統一)
    normalized = unicodedata.normalize('NFKC', str(text))
    return normalized.strip()

# --- 3. 時程表（Excel）の読み込み ---
def read_excel_schedule(file_stream):
    try:
        # header=Noneで読み込み、後で1行目を整形する
        full_df = pd.read_excel(file_stream, header=None).fillna('')
        location_data_dic = {}
        
        # A列(iloc[:,0])が空でない行を勤務地の区切り(Key)とする
        loc_idx = full_df[full_df.iloc[:, 0].astype(str).str.strip() != ""].index.tolist()
        
        for i, start_row in enumerate(loc_idx):
            raw_name = str(full_df.iloc[start_row, 0]).strip()
            # 比較用に地名をクリーン化 (空白除去)
            norm_name = re.sub(r'\s+', '', unicodedata.normalize('NFKC', raw_name)).upper()
            if not norm_name: continue
            
            end_row = loc_idx[i+1] if i+1 < len(loc_idx) else len(full_df)
            df_block = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
            
            # 【重要】時程表の1行目（時間表示）をHH:MMに整形
            # 通常3列目以降が時間軸であることを想定
            for col in range(3, df_block.shape[1]):
                val = df_block.iloc[0, col]
                df_block.iloc[0, col] = format_to_hhmm(val)
                
            location_data_dic[norm_name] = df_block
        return location_data_dic
    except Exception as e:
        print(f"Excel Read Error: {e}")
        return None

# --- 4. PDF読み込み関数 (本町2段構成・記号対応) ---
def pdf_reader(pdf_stream, target_staff):
    table_dictionary = {}
    clean_target = re.sub(r'\s+', '', unicodedata.normalize('NFKC', target_staff))
    
    # 判定対象キーワード
    location_keywords = ["T1", "T2", "札幌", "羽田", "本町"]
    
    try:
        with pdfplumber.open(pdf_stream) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                norm_page_text = re.sub(r'\s+', '', unicodedata.normalize('NFKC', page_text)).upper()
                
                # ページデフォルトの勤務地を判定
                page_default_loc = "UNKNOWN"
                for kw in location_keywords:
                    if kw in norm_page_text:
                        page_default_loc = kw
                        break
                
                tables = page.extract_tables()
                for table in tables:
                    if not table: continue
                    
                    processed_table = []
                    for row in table:
                        # 【重要】セル内の改行を「 / 」に置換して2段構成(開始/終了)を保持
                        processed_row = [normalize_text(cell).replace('\n', ' / ') for cell in row]
                        processed_table.append(processed_row)
                        
                    df = pd.DataFrame(processed_table).fillna('')
                    if df.empty or df.shape[1] < 2: continue
                    
                    # 氏名検索用(0列目)
                    col_0_search = [re.sub(r'\s+', '', str(val)) for val in df.iloc[:, 0].tolist()]
                    
                    if clean_target in col_0_search:
                        idx = col_0_search.index(clean_target)
                        
                        # 勤務地の詳細特定 (氏名セル -> 1つ上 -> 左上 の優先順)
                        specific_loc = page_default_loc
                        check_cells = [df.iloc[idx, 0], df.iloc[max(0, idx-1), 0], df.iloc[0, 0]]
                        for cell_val in check_cells:
                            norm_val = re.sub(r'\s+', '', str(cell_val)).upper()
                            found = False
                            for kw in location_keywords:
                                if kw in norm_val:
                                    specific_loc = kw
                                    found = True
                                    break
                            if found: break
                        
                        # 自分のシフト (氏名行とその下の行の2行1セットを維持)
                        my_daily_shift = df.iloc[idx : idx+2].copy().reset_index(drop=True)
                        
                        # 同僚のシフト (自分以外)
                        other_indices = [i for i in range(len(df)) if i not in [idx, idx+1]]
                        other_daily_shift = df.iloc[other_indices].copy().reset_index(drop=True)
                        
                        table_dictionary[specific_loc] = [my_daily_shift, other_daily_shift]
                        
    except Exception as e:
        print(f"PDF Reader Error: {e}")
        
    return table_dictionary

# --- 5. データ統合関数 ---
def data_integration(pdf_dic, time_schedule_dic):
    integrated_data = {}
    for pdf_loc, pdf_data in pdf_dic.items():
        matched_key = None
        # PDFの勤務地名とExcelの勤務地名を照合
        for ex_key in time_schedule_dic.keys():
            if pdf_loc == ex_key or pdf_loc in ex_key or ex_key in pdf_loc:
                matched_key = ex_key
                break
        
        if matched_key:
            # 自分のシフト, 同僚のシフト, 対応する時程表
            integrated_data[pdf_loc] = [pdf_data[0], pdf_data[1], time_schedule_dic[matched_key]]
    return integrated_data
