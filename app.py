import pandas as pd
import pdfplumber
import re
import io
import unicodedata

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
    # 全角半角の統一と、不要な空白・改行の除去
    normalized = unicodedata.normalize('NFKC', str(text))
    return re.sub(r'[\s　\n\r]', '', normalized).strip()

# --- 3. 時程表（Excel）の読み込み ---
def read_excel_schedule(file_stream):
    try:
        full_df = pd.read_excel(file_stream, header=None).fillna('')
        location_data_dic = {}
        
        # A列(index 0)が空でない行のインデックスを抽出
        loc_idx = full_df[full_df.iloc[:, 0].astype(str).str.strip() != ""].index.tolist()
        
        for i, start_row in enumerate(loc_idx):
            raw_name = str(full_df.iloc[start_row, 0]).strip()
            norm_name = normalize_text(raw_name)
            if not norm_name: continue
            
            end_row = loc_idx[i+1] if i+1 < len(loc_idx) else len(full_df)
            df_block = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
            
            for col in range(3, df_block.shape[1]):
                df_block.iloc[0, col] = format_to_hhmm(df_block.iloc[0, col])
                
            location_data_dic[norm_name] = df_block
        return location_data_dic
    except Exception as e:
        print(f"Excel Read Error: {e}")
        return None

# --- 4. PDF読み込み関数 ---
def pdf_reader(pdf_stream, target_staff):
    """
    PDF内の各ページから勤務地を動的に特定します。
    """
    table_dictionary = {}
    clean_target = normalize_text(target_staff)
    
    try:
        with pdfplumber.open(pdf_stream) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                
                # 勤務地特定ロジック
                target_index = len(lines) // 2
                if target_index < len(lines):
                    work_place_raw = lines[target_index]
                else:
                    work_place_raw = lines[-1] if lines else "unknown"
                
                work_place = normalize_text(work_place_raw)
                
                tables = page.extract_tables()
                for table in tables:
                    if not table: continue
                    df = pd.DataFrame(table).fillna('')
                    if df.empty or df.shape[1] < 2: continue
                    
                    # テーブルの左上に特定した勤務地をセット
                    df.iloc[0, 0] = work_place
                    
                    # --- 修正箇所：氏名検索の安定化 ---
                    # 0列目をリストとして取得し、各要素を正規化して比較する
                    names_list = [normalize_text(str(val)) for val in df.iloc[:, 0].tolist()]
                    
                    if clean_target in names_list:
                        # 最初に一致したインデックスを取得
                        idx = names_list.index(clean_target)
                        
                        # 自分(2行)と他人(ヘッダーと自分以外)
                        my_daily_shift = df.iloc[idx : idx+2].copy().reset_index(drop=True)
                        
                        # 他人のデータ抽出
                        # df.index と idx, idx+1 を比較して除外
                        other_indices = [i for i in range(len(df)) if i not in [0, idx, idx+1]]
                        other_daily_shift = df.iloc[other_indices].copy().reset_index(drop=True)
                        
                        table_dictionary[work_place] = [my_daily_shift, other_daily_shift]
                        
    except Exception as e:
        # Streamlit上でエラーを確認できるよう print ではなく例外を出すか詳細を記録
        print(f"PDF Reader Error: {e}")
        
    return table_dictionary

# --- 5. データ統合関数 ---
def data_integration(pdf_dic, time_schedule_dic):
    integrated_data = {}
    for loc_key, pdf_data in pdf_dic.items():
        if loc_key in time_schedule_dic:
            integrated_data[loc_key] = [pdf_data[0], pdf_data[1], time_schedule_dic[loc_key]]
    return integrated_data
