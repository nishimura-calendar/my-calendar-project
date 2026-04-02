import pandas as pd
import pdfplumber
import unicodedata
import re
import io
from datetime import datetime

# --- 1. 比較・整形用共通関数 ---
def normalize_for_match(text):
    if text is None or str(text).lower() == 'nan': 
        return ""
    normalized = unicodedata.normalize('NFKC', str(text))
    return re.sub(r'\s+', '', normalized).strip().upper()

# --- 2. 詳細シフト計算 ---
def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
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

# --- 3. PDF解析：年月取得と拠点別データ抽出 ---
def pdf_reader(file_stream, target_staff):
    table_dictionary = {}
    date_info = {"year": None, "month": None}
    clean_target = normalize_for_match(target_staff)

    # 拠点名として認めないキーワードリスト
    ignore_keywords = ["氏名", "名前", "担当", "ランク", "NO", "番号", "区分", "合計", "備考"]

    with pdfplumber.open(file_stream) as pdf:
        full_text = ""
        for page in pdf.pages[:2]:
            full_text += page.extract_text() or ""
        
        date_match = re.search(r'(\d{4})\s*年\s*(\d{1,2})\s*月', full_text)
        if date_match:
            date_info["year"] = int(date_match.group(1))
            date_info["month"] = int(date_match.group(2))

        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                df = pd.DataFrame(table)
                if df.empty: continue
                
                search_col = df.iloc[:, 0].apply(normalize_for_match)
                
                if clean_target in search_col.values:
                    indices = search_col[search_col == clean_target].index
                    for idx in indices:
                        # --- 拠点名(勤務地)抽出の安定化ロジック (改良版) ---
                        work_place = ""
                        # 1列目〜4列目をスキャン
                        for col_idx in range(1, min(5, len(df.columns))):
                            val = str(df.iloc[idx, col_idx]).strip()
                            
                            # 判定条件：
                            # 1. 2文字以上
                            # 2. 数字のみではない
                            # 3. 除外キーワードを含まない
                            is_ignored = any(kw in val for kw in ignore_keywords)
                            
                            if val and len(val) >= 2 and not val.isdigit() and not is_ignored:
                                work_place = val
                                break
                        
                        # 適切な拠点名が見つかった場合のみ処理を続行
                        if work_place:
                            my_data = df.iloc[[idx]].copy()
                            # 同拠点スタッフの抽出 (拠点名が見つかった列 col_idx を基準に判定)
                            others_data = df[(df.iloc[:, col_idx] == work_place) & (search_col != clean_target)].copy()
                            
                            table_dictionary[work_place] = [
                                my_data.reset_index(drop=True), 
                                others_data.reset_index(drop=True)
                            ]
    return date_info, table_dictionary

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
def process_integrated_data(integrated_dic, date_info, current_col):
    all_final_rows = []
    
    # 日付オフセット（PDFの構造により調整が必要な場合があります）
    # 氏名(0), 拠点(1), ランク(2) と続く場合、1日は4列目(3)から。
    offset = 2 
    day = current_col - offset 
    
    if date_info["year"] and date_info["month"] and day > 0:
        target_date_str = f"{date_info['year']}-{date_info['month']:02d}-{day:02d}"
    else:
        target_date_str = datetime.now().strftime("%Y-%m-%d")

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
