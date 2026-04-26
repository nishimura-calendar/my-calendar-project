import pandas as pd
import re
import unicodedata
import os
import camelot
import calendar
import math

def normalize_text(text):
    if not isinstance(text, str): return ""
    text = unicodedata.normalize('NFKC', text)
    return re.sub(r'[\s　]', '', text).lower()

def extract_year_month_from_text(text):
    """【ファイル名=正】年月から期待される日数と第一曜日を算出"""
    if not text: return None
    text = unicodedata.normalize('NFKC', text)
    clean_text = re.sub(r'\s+', '', text)
    y_match = re.search(r'(\d{4})', clean_text)
    m_match = re.search(r'(\d{1,2})月', clean_text)
    if not y_match or not m_match: return None

    y_val, m_val = int(y_match.group(1)), int(m_match.group(1))
    first_wd_num, days_in_month = calendar.monthrange(y_val, m_val)
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    return {
        "year": y_val, 
        "month": m_val, 
        "days": days_in_month, 
        "first_wd": weekdays_jp[first_wd_num]
    }

def time_schedule_from_drive(sheets_service, file_id):
    """時程表(正)を読み込み、勤務地をkeyとして辞書に登録"""
    spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=file_id).execute()
    sheets = spreadsheet.get('sheets', [])
    location_data_dic = {}
    for s in sheets:
        title = s.get("properties", {}).get("title")
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=file_id, range=f"'{title}'!A1:Z200").execute()
        vals = result.get('values', [])
        if not vals: continue
        
        df = pd.DataFrame(vals)
        # 列名重複回避処理
        raw_cols = [str(c).strip() if c else f"Unnamed_{i}" for i, c in enumerate(df.iloc[0])]
        new_cols = []
        counts = {}
        for col in raw_cols:
            if col in counts:
                counts[col] += 1
                new_cols.append(f"{col}_{counts[col]}")
            else:
                counts[col] = 0
                new_cols.append(col)
        df.columns = new_cols
        df = df[1:].reset_index(drop=True)
        
        # A列(勤務地)補完
        first_col = df.columns[0]
        df[first_col] = df[first_col].replace('', None).ffill()
        
        for loc in df[first_col].unique():
            if not loc: continue
            location_data_dic[normalize_text(str(loc))] = {
                "df": df[df[first_col] == loc].fillna('').reset_index(drop=True),
                "original_name": str(loc)
            }
    return location_data_dic

def pdf_reader(pdf_stream, target_staff, expected_info, time_dic):
    """
    【最終定義：絶対座標と列区分】
    1. 勤務地: iloc[1, 0] を時程表キーと照合
    2. 日付区分: iloc[0, 1] ～ iloc[0, days] (列区分)
    3. 曜日区分: iloc[1, 1] ～ iloc[1, days] (列区分)
    4. 描画座標: math.ceilを用いた中線・底罫線の算出
    """
    pdf_stream.seek(0)
    temp_name = "temp_process.pdf"
    with open(temp_name, "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    try:
        tables = camelot.read_pdf(temp_name, pages='all', flavor='lattice')
        res = {}
        
        for table in tables:
            df = table.df
            if df.empty or len(df) < 3: continue
            
            # --- 第一関門: 勤務地特定 (iloc[1,0]付近をマスターと照合) ---
            cell_1_0_raw = str(df.iloc[1, 0])
            work_place_name = "Unknown"
            found_key = None
            for t_key, t_val in time_dic.items():
                if t_val["original_name"] in cell_1_0_raw:
                    work_place_name = t_val["original_name"]
                    found_key = t_key
                    break
            if not found_key: continue

            # --- 第二関門: 整合性チェック (列の末尾と1日の曜日) ---
            pdf_days_val = re.sub(r'\D', '', str(df.iloc[0, -1]))
            pdf_first_wd = str(df.iloc[1, 1]).strip()
            
            if pdf_days_val != str(expected_info["days"]) or pdf_first_wd != expected_info["first_wd"]:
                return {"error": f"不一致：期待({expected_info['days']}/{expected_info['first_wd']}) PDF({pdf_days_val}/{pdf_first_wd})", "df": df}

            # --- 座標計算 (中線・底罫線仕様) ---
            search_col_all = df.iloc[:, 0].astype(str)
            max_name_len = search_col_all.apply(len).max()
            x_border = math.ceil(max(len(work_place_name), max_name_len))
            
            h_date, h_week = 10.0, 10.0 # 仮定高さ
            y_mid_line = math.ceil(h_date)
            bottom_border = math.ceil(h_date + h_week)

            # --- 第三関門: スタッフ抽出 (3行目以降から検索) ---
            clean_target = normalize_text(target_staff)
            staff_area = df.iloc[2:, 0].astype(str).apply(normalize_text)
            matches = staff_area[staff_area == clean_target].index.tolist()
            
            if matches:
                idx = matches[0]
                # 列の区分を維持して抽出 (0列目=名前, 1列目以降=日付データ)
                my_shift = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
                others = df.drop([0, 1, idx, idx+1] if idx+1 < len(df) else [0, 1, idx]).copy().reset_index(drop=True)
                
                res[found_key] = {
                    "my_shift": my_shift,
                    "others": others,
                    "wp_name": work_place_name,
                    "drawing": {"x": x_border, "y": y_mid_line, "bottom": bottom_border},
                    "header_date": df.iloc[0, :].tolist(), # 日付列の区分
                    "header_week": df.iloc[1, :].tolist()  # 曜日列の区分
                }
        return res
    finally:
        if os.path.exists(temp_name): os.remove(temp_name)
