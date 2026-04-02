import pandas as pd
import pdfplumber
import unicodedata
import re

def normalize_for_match(text):
    """比較用にテキストを正規化（全角半角統一、空白・改行除去）"""
    if text is None or str(text).lower() == 'nan': 
        return ""
    normalized = unicodedata.normalize('NFKC', str(text))
    return re.sub(r'[\s\n]+', '', normalized).strip().upper()

def pdf_reader(file_stream, target_staff):
    """
    1. ページ内のテーブルをスキャン
    2. 名前が見つかったテーブルを特定
    3. 左上セル(0,0)の改行数をカウントし、その半分(count // 2)の位置から勤務地を抽出
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
                found_indices = [i for i, val in enumerate(search_col) if clean_target in val]
                
                if found_indices:
                    # --- 勤務地の特定ロジック (改行カウント方式) ---
                    header_cell = str(df.iloc[0, 0])
                    lines = header_cell.split('\n')
                    
                    try:
                        num_newlines = header_cell.count('\n')
                        # ユーザー考案: 改行数の半分をインデックスにする
                        target_index = num_newlines // 2
                        
                        if target_index < len(lines):
                            work_place = lines[target_index].strip()
                        else:
                            work_place = lines[-1].strip() if lines else "不明"
                            
                        # 空文字だった場合のフォールバック
                        if not work_place:
                            non_empty_elements = [e.strip() for e in lines if e.strip()]
                            work_place = non_empty_elements[1] if len(non_empty_elements) >= 2 else non_empty_elements[0]
                    except Exception:
                        work_place = "解析エラー"
                    
                    for idx in found_indices:
                        my_data = df.iloc[[idx]].copy()
                        others_data = df[df.index != idx].copy()
                        
                        # 特定した勤務地をキーとして辞書を作成
                        table_dictionary[work_place] = [
                            my_data.reset_index(drop=True), 
                            others_data.reset_index(drop=True)
                        ]
                        
    return table_dictionary

def data_integration(pdf_dic, time_schedule_dic):
    """
    PDFから抽出した勤務地（例: T2）と、時程表（例: 大阪拠点）を紐付ける。
    エラー回避のため、必ず辞書を返すようにする。
    """
    integrated_dic = {}
    if not pdf_dic:
        return integrated_dic
    
    # 時程表が空の場合のガード
    if not time_schedule_dic:
        return integrated_dic

    for place_name, pdf_data in pdf_dic.items():
        norm_place = normalize_for_match(place_name)
        matched_key = None
        
        # 時程表のキー（拠点名）と部分一致を確認
        for k in time_schedule_dic.keys():
            norm_k = normalize_for_match(k)
            # PDF側の「T2」が時程表の「大阪拠点(T2)」に含まれる、あるいはその逆をチェック
            if norm_k in norm_place or norm_place in norm_k:
                matched_key = k
                break
        
        # もし見つからず、時程表が1つしかない場合は、それを割り当てる（柔軟な紐付け）
        if not matched_key and len(time_schedule_dic) == 1:
            matched_key = list(time_schedule_dic.keys())[0]
            
        if matched_key:
            # pdf_data[0]: 本人, pdf_data[1]: 他人, time_schedule_dic[matched_key]: 時程表
            integrated_dic[place_name] = [pdf_data[0], pdf_data[1], time_schedule_dic[matched_key]]
            
    return integrated_dic

def shift_cal(place_key, target_date, col, shift_code, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """詳細な時間計算ロジック（交代相手の特定など）"""
    sched_clean = time_schedule.fillna("").astype(str)
    # シフトコード（A, Bなど）に一致する行を時程表から探す
    # 時程表の2列目(index 1)にシフトコードがある前提
    my_time_shift = sched_clean[sched_clean.iloc[:, 1] == shift_code]
                    
    if not my_time_shift.empty:
        prev_val = ""
        for t_col in range(2, time_schedule.shape[1]):
            current_val = my_time_shift.iloc[0, t_col]
            
            if current_val != prev_val:
                if current_val != "": 
                    # 交代の有無を確認
                    handing_over_department = "" 
                    mask_handing_over = (sched_clean.iloc[:, t_col] == prev_val) & (sched_clean.iloc[:, 1] != shift_code)
                    mask_taking_over = (sched_clean.iloc[:, t_col] == current_val) & (sched_clean.iloc[:, 1] != shift_code)
                    
                    if mask_handing_over.any():
                        handing_over_department = "(交代)"
                    
                    # 交代相手の名前を取得
                    handing_over = ""
                    taking_over = ""
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
                    # 勤務終了時間を設定
                    if len(final_rows) > 0 and final_rows[-1][5] == "False":
                        final_rows[-1][4] = time_schedule.iloc[0, t_col]
            
            prev_val = current_val

def process_integrated_data(integrated_dic, target_date_str, current_col):
    """紐付けられたデータからCSV用の行を生成する"""
    all_final_rows = []
    
    for place_key, data_list in integrated_dic.items():
        my_shift, other_shift, time_sched = data_list
        if current_col >= len(my_shift.columns): continue
        
        raw_val = str(my_shift.iloc[0, current_col])
        # 改行やカンマで区切られたシフトコードを分割
        items = [i.strip() for i in re.split(r'[,、\s\n]+', raw_val) if i.strip()]
        # 時程表に存在するコードか確認するためのリスト
        master_codes_norm = [normalize_for_match(x) for x in time_sched.iloc[:, 1].tolist()]
        
        for item in items:
            norm_item = normalize_for_match(item)
            if norm_item in master_codes_norm:
                # 時程表にあるコードなら詳細計算を行う
                all_final_rows.append([f"{place_key}{item}", target_date_str, "", target_date_str, "", "True", "", ""])
                shift_cal(place_key, target_date_str, current_col, item, my_shift, other_shift, time_sched, all_final_rows)
            else:
                # 時程表にないコード（公休、有休など）はそのまま出力
                all_final_rows.append([item, target_date_str, "", target_date_str, "", "True", "", ""])
                
    return all_final_rows
