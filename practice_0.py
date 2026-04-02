import pandas as pd
import pdfplumber
import unicodedata
import re
import io

# --- 1. 比較・整形用共通関数 ---
def normalize_for_match(text):
    """全角半角、空白を統一して比較可能な状態にする"""
    if text is None or str(text).lower() == 'nan': 
        return ""
    normalized = unicodedata.normalize('NFKC', str(text))
    return re.sub(r'\s+', '', normalized).strip().upper()

# --- 2. 詳細シフト計算 ---
def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """通常シフトの詳細（時間別引き継ぎ）を計算し、final_rowsに格納する"""
    shift_code = my_daily_shift.iloc[0, col]
    sched_clean = time_schedule.fillna("").astype(str)
    my_time_shift = sched_clean[sched_clean.iloc[:, 1] == shift_code]
                    
    if not my_time_shift.empty:
        prev_val = ""
        for t_col in range(2, time_schedule.shape[1]):
            current_val = my_time_shift.iloc[0, t_col]
            
            if current_val != prev_val:
                if current_val != "": 
                    handing_over_department = "" 
                    mask_handing_over = (sched_clean.iloc[:, t_col] == prev_val) & (sched_clean.iloc[:, 1] != shift_code)
                    mask_taking_over = (sched_clean.iloc[:, t_col] == current_val) & (sched_clean.iloc[:, 1] != shift_code)
                    
                    if mask_handing_over.any():
                        handing_over_department = "(交代)"
                    else:
                        handing_over_department = ""
                    
                    for i in range(2):
                        mask = mask_handing_over if i == 0 else mask_taking_over
                        search_keys = time_schedule.loc[mask, time_schedule.columns[1]]
                        target_rows = other_staff_shift[other_staff_shift.iloc[:, col].isin(search_keys)]
                        names_series = target_rows.iloc[:, 0]
                        
                        if i == 0:
                            staff_names = f"to {'・'.join(names_series.unique().astype(str))}" if not names_series.empty else ""
                            handing_over = f"{handing_over_department}{staff_names}"
                        else:
                            staff_names = f"from {'・'.join(names_series.unique().astype(str))}" if not names_series.empty else ""
                            taking_over = f"【{current_val}】{staff_names}"    
                    
                    final_rows.append([
                        f"{handing_over}=>{taking_over}", 
                        target_date, 
                        time_schedule.iloc[0, t_col], 
                        target_date, 
                        "", 
                        "False", 
                        "", 
                        ""
                    ])
                else:
                    if len(final_rows) > 0 and final_rows[-1][5] == "False":
                        final_rows[-1][4] = time_schedule.iloc[0, t_col]
            
            prev_val = current_val

# --- 3. PDF解析：昨日と同じシンプルな抽出 ---
def pdf_reader(file_stream, target_staff):
    """
    PDFから本人のデータを探し、拠点名を取得して辞書化する。
    """
    table_dictionary = {}
    clean_target = normalize_for_match(target_staff)

    with pdfplumber.open(file_stream) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                df = pd.DataFrame(table)
                if df.empty: continue
                
                # 0列目を氏名として検索
                search_col = df.iloc[:, 0].apply(normalize_for_match)
                
                if clean_target in search_col.values:
                    indices = search_col[search_col == clean_target].index
                    for idx in indices:
                        # 拠点名の取得列を調整してください。
                        # もし「C」が1列目(index 1)にあるなら、2列目(index 2)が拠点名かもしれません。
                        # 昨日の成功時に合わせて 1 または 2 に設定します。
                        work_place = str(df.iloc[idx, 1]).strip()
                        
                        # もし work_place が "C" などの1文字で、本来の拠点が隣にあるなら
                        # ここを df.iloc[idx, 2] に変える必要があります。
                        
                        if work_place:
                            my_data = df.iloc[[idx]].copy()
                            others_data = df[(df.iloc[:, 1] == work_place) & (search_col != clean_target)].copy()
                            
                            table_dictionary[work_place] = [
                                my_data.reset_index(drop=True), 
                                others_data.reset_index(drop=True)
                            ]
    return table_dictionary

# --- 4. データ統合関数 ---
def data_integration(pdf_dic, time_schedule_dic):
    integrated_dic = {}
    if not pdf_dic: return integrated_dic
    
    for place_name, pdf_data in pdf_dic.items():
        norm_place = normalize_for_match(place_name)
        matched_key = None
        for k in time_schedule_dic.keys():
            norm_k = normalize_for_match(k)
            if norm_k in norm_place or norm_place in norm_k:
                matched_key = k
                break
        
        if matched_key:
            integrated_dic[place_name] = [pdf_data[0], pdf_data[1], time_schedule_dic[matched_key]]
    return integrated_dic

# --- 5. CSV行生成 ---
def process_integrated_data(integrated_dic, target_date_str, current_col):
    all_final_rows = []
    
    for place_key, data_list in integrated_dic.items():
        my_shift, other_shift, time_sched = data_list
        if current_col >= len(my_shift.columns): continue
        
        raw_val = str(my_shift.iloc[0, current_col])
        items = [i.strip() for i in re.split(r'[,、\s\n]+', raw_val) if i.strip()]
        master_codes_norm = [normalize_for_match(x) for x in time_sched.iloc[:, 1].tolist()]
        
        for item in items:
            norm_item = normalize_for_match(item)
            if norm_item in master_codes_norm:
                all_final_rows.append([f"{place_key}{item}", target_date_str, "", target_date_str, "", "True", "", ""])
                shift_cal(place_key, target_date_str, current_col, item, my_shift, other_shift, time_sched, all_final_rows)
            else:
                all_final_rows.append([item, target_date_str, "", target_date_str, "", "True", "", ""])
    return all_final_rows
