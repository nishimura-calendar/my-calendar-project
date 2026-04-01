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
    normalized = unicodedata.normalize('NFKC', str(text))
    # 比較用には空白を除去したものを利用
    return re.sub(r'[\s　\n\r]', '', normalized).strip().upper()

# --- 3. 時程表（Excel）の読み込み ---
def read_excel_schedule(file_stream):
    try:
        full_df = pd.read_excel(file_stream, header=None).fillna('')
        location_data_dic = {}
        # A列が空でない行を勤務地開始行とする
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
    except:
        return None

# --- 4. PDF読み込み関数 (表の左上をそのまま維持する版) ---
def pdf_reader(pdf_stream, target_staff):
    """
    PDFからテーブルを抽出し、左上(0,0)の値をそのままキーとして採用、
    または表示用データとして維持します。
    """
    table_dictionary = {}
    clean_target = normalize_text(target_staff)
    
    try:
        with pdfplumber.open(pdf_stream) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                if not tables:
                    continue
                
                for table in tables:
                    if not table: continue
                    df = pd.DataFrame(table).fillna('')
                    if df.empty or df.shape[1] < 2: continue
                    
                    # 1. 表の左上(0,0)にある値をそのまま取得
                    raw_loc_val = str(df.iloc[0, 0]).strip()
                    # 表示用に改行などを整理
                    display_loc = raw_loc_val.replace('\n', ' ')
                    
                    # 2. 0列目(氏名列)を正規化して検索
                    names_list = [normalize_text(str(val)) for val in df.iloc[:, 0].tolist()]
                    
                    if clean_target in names_list:
                        idx = names_list.index(clean_target)
                        
                        # --- 自分のシフト (2行) ---
                        my_daily_shift = df.iloc[idx : idx+2].copy().reset_index(drop=True)
                        
                        # --- 同僚のシフト (ヘッダーと自分以外) ---
                        # 0行目(場所/日付ヘッダー)と自分を除外
                        other_indices = [i for i in range(len(df)) if i not in [idx, idx+1]]
                        other_daily_shift = df.iloc[other_indices].copy().reset_index(drop=True)
                        
                        # 辞書のキーには、左上の値を正規化したものを使用
                        key_name = normalize_text(raw_loc_val) if normalize_text(raw_loc_val) != "" else f"Page_{page.page_number}"
                        
                        # リスト形式で格納 [自分, 他人]
                        table_dictionary[key_name] = [my_daily_shift, other_daily_shift]
                        
    except Exception as e:
        print(f"PDF Reader Error: {e}")
        
    return table_dictionary

# --- 5. データ統合関数 (独立表示用には使用しないが互換性のため維持) ---
def data_integration(pdf_dic, time_schedule_dic):
    integrated_data = {}
    for loc_key, pdf_data in pdf_dic.items():
        if loc_key in time_schedule_dic:
            integrated_data[loc_key] = [pdf_data[0], pdf_data[1], time_schedule_dic[loc_key]]
    return integrated_data
