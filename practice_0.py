import pandas as pd
import pdfplumber
import unicodedata
import re

def normalize_for_match(text):
    """
    全角半角の統一、空白・改行を完全に除去して比較用の文字列を生成する。
    """
    if text is None or str(text).lower() == 'nan': 
        return ""
    normalized = unicodedata.normalize('NFKC', str(text))
    return re.sub(r'[\s\n]+', '', normalized).strip().upper()

def extract_workplace_from_header(header_text):
    """
    セルの改行数を数え、その中心付近にある文字列を勤務地として抽出する。
    例: "1\n\nT2\n\n木" -> 改行4つ -> インデックス2の "T2" を取得。
    """
    if not header_text or header_text == "None":
        return "不明な拠点"
    
    lines = header_text.split('\n')
    num_newlines = header_text.count('\n')
    
    # ユーザー考案ロジック: 改行数の半分をインデックスにする
    target_index = num_newlines // 2
    
    try:
        if target_index < len(lines):
            work_place = lines[target_index].strip()
        else:
            work_place = lines[-1].strip()
            
        # もし空文字だった場合は、空でない要素の2番目を取得（フォールバック）
        if not work_place:
            non_empty = [e.strip() for e in lines if e.strip()]
            if len(non_empty) >= 2:
                work_place = non_empty[1] # [日付, 勤務地, 曜日] の想定
            elif len(non_empty) == 1:
                work_place = non_empty[0]
            else:
                work_place = "不明な拠点"
        return work_place
    except Exception:
        return "解析エラー"

def pdf_reader(file_stream, target_staff):
    """
    処理順序：
    1. 各テーブルごとにまず「勤務地」を特定する。
    2. そのテーブル内で target_staff を検索する。
    3. スタッフが見つかった場合のみ、その勤務地をキーとしてデータを登録する。
    4. スタッフがいなければそのテーブル（勤務地）は読み込まない（スキップ）。
    """
    table_dictionary = {}
    clean_target = normalize_for_match(target_staff)

    with pdfplumber.open(file_stream) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                df = pd.DataFrame(table)
                if df.empty or df.shape[1] < 1:
                    continue
                
                # --- STEP 1: 勤務地の特定 ---
                # テーブルの(0,0)セルから勤務地を抽出
                header_val = str(df.iloc[0, 0])
                current_workplace = extract_workplace_from_header(header_val)
                
                # --- STEP 2: 特定スタッフの検索 ---
                # 0列目を氏名列としてスキャン
                search_col = df.iloc[:, 0].apply(normalize_for_match)
                found_indices = [i for i, val in enumerate(search_col) if clean_target in val]
                
                # --- STEP 3: 登録判定 ---
                if not found_indices:
                    # スタッフがいなければこの勤務地(テーブル)はスキップ
                    continue
                
                # スタッフが見つかった場合のみ辞書に追加
                # 複数箇所に同じ名前がある場合（あるいは同姓同名）も考慮してリストを管理
                for idx in found_indices:
                    my_data = df.iloc[[idx]].copy()
                    others_data = df[df.index != idx].copy()
                    
                    # 既に同じ勤務地名が登録されている場合は、別のキー（例: T2_2）にするか統合
                    key_name = current_workplace
                    counter = 2
                    while key_name in table_dictionary:
                        key_name = f"{current_workplace}_{counter}"
                        counter += 1
                        
                    table_dictionary[key_name] = [
                        my_data.reset_index(drop=True), 
                        others_data.reset_index(drop=True)
                    ]
                        
    return table_dictionary

def data_integration(pdf_dic, time_schedule_dic):
    """
    抽出された勤務地(T2など)と、時程表(Drive側)のマスターデータを紐付ける。
    """
    integrated_dic = {}
    if not pdf_dic or not time_schedule_dic:
        return integrated_dic

    for place_name, pdf_data in pdf_dic.items():
        # place_name は "T2" や "T2_2" など
        norm_place = normalize_for_match(place_name)
        matched_key = None
        
        for k in time_schedule_dic.keys():
            norm_k = normalize_for_match(k)
            # 時程表名に "T2" が含まれる、あるいはPDF側の名前に時程表名が含まれるか
            if norm_k in norm_place or norm_place in norm_k:
                matched_key = k
                break
        
        # フォールバック：時程表が1つならそれを割り当てる
        if not matched_key and len(time_schedule_dic) == 1:
            matched_key = list(time_schedule_dic.keys())[0]
            
        if matched_key:
            integrated_dic[place_name] = [pdf_data[0], pdf_data[1], time_schedule_dic[matched_key]]
            
    return integrated_dic

def shift_cal(place_key, target_date, col, shift_code, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """詳細なシフト時間および交代相手の計算"""
    sched_clean = time_schedule.fillna("").astype(str)
    my_time_shift = sched_clean[sched_clean.iloc[:, 1] == shift_code]
                    
    if not my_time_shift.empty:
        prev_val = ""
        for t_col in range(2, time_schedule.shape[1]):
            current_val = my_time_shift.iloc[0, t_col]
            if current_val != prev_val:
                if current_val != "": 
                    mask_handing_over = (sched_clean.iloc[:, t_col] == prev_val) & (sched_clean.iloc[:, 1] != shift_code)
                    mask_taking_over = (sched_clean.iloc[:, t_col] == current_val) & (sched_clean.iloc[:, 1] != shift_code)
                    
                    handing_over = ""
                    taking_over = ""
                    for i in range(2):
                        mask = mask_handing_over if i == 0 else mask_taking_over
                        codes = time_schedule.loc[mask, time_schedule.columns[1]]
                        targets = other_staff_shift[other_staff_shift.iloc[:, col].isin(codes)]
                        names = '・'.join(targets.iloc[:, 0].unique().astype(str))
                        if i == 0:
                            handing_over = f"(交代)to {names}" if names else ""
                        else:
                            taking_over = f"【{current_val}】from {names}" if names else f"【{current_val}】"
                    
                    final_rows.append([
                        f"{handing_over}=>{taking_over}", target_date, time_schedule.iloc[0, t_col], 
                        target_date, "", "False", "", place_key
                    ])
                else:
                    if len(final_rows) > 0 and final_rows[-1][5] == "False":
                        final_rows[-1][4] = time_schedule.iloc[0, t_col]
            prev_val = current_val

def process_integrated_data(integrated_dic, target_date_str, current_col):
    """CSV出力用データの生成"""
    all_final_rows = []
    for place_key, data_list in integrated_dic.items():
        my_shift, other_shift, time_sched = data_list
        if current_col >= len(my_shift.columns): continue
        
        raw_val = str(my_shift.iloc[0, current_col])
        items = [i.strip() for i in re.split(r'[,、\s\n]+', raw_val) if i.strip()]
        master_codes = [normalize_for_match(x) for x in time_sched.iloc[:, 1].tolist()]
        
        for item in items:
            norm_item = normalize_for_match(item)
            if norm_item in master_codes:
                all_final_rows.append([f"{place_key}:{item}", target_date_str, "", target_date_str, "", "True", "", place_key])
                shift_cal(place_key, target_date_str, current_col, item, my_shift, other_shift, time_sched, all_final_rows)
            else:
                all_final_rows.append([item, target_date_str, "", target_date_str, "", "True", "", place_key])
    return all_final_rows
