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
    """ファイル名に『2026年1月』などの年月が必須の状態に戻します"""
    if not text: return None
    text = unicodedata.normalize('NFKC', text)
    y_match = re.search(r'(\d{4})', text)
    m_match = re.search(r'(\d{1,2})月', text)
    
    # 月が見つからない場合はここで処理を中断（午前中の仕様）
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
    """スプレッドシートから時程マスターを読み込み"""
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
        df.columns = [f"col_{i}" for i in range(df.shape[1])]
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
    """絶対座標(1-2行目ヘッダー、3行目〜人名)のロジックに戻します"""
    pdf_stream.seek(0)
    temp_name = "temp_process.pdf"
    with open(temp_name, "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    try:
        tables = camelot.read_pdf(temp_name, pages='all', flavor='lattice')
        res = {}
        
        for table in tables:
            df = table.df.replace(r'[\r\n]', '', regex=True)
            if df.empty or len(df) < 3: continue
            
            # 1. 勤務地特定 (iloc[1,0]付近をマスターと照合)
            cell_1_0_raw = normalize_text(str(df.iloc[1, 0]))
            found_key = None
            work_place_name = "Unknown"
            for t_key, t_val in time_dic.items():
                if t_key in cell_1_0_raw:
                    found_key = t_key
                    work_place_name = t_val["original_name"]
                    break
            if not found_key: continue

            # 2. 整合性チェック (日数と1日の曜日)
            pdf_days = re.sub(r'\D', '', str(df.iloc[0, -1]))
            pdf_first_wd = str(df.iloc[1, 1]).strip()
            
            if pdf_days != str(expected_info["days"]) or pdf_first_wd != expected_info["first_wd"]:
                # 午前中の成功状態：一致しない表は無視する
                continue

            # 3. スタッフ抽出 (3行目以降から人名を検索)
            target_norm = normalize_text(target_staff)
            staff_area = df.iloc[2:, 0].astype(str).apply(normalize_text)
            match_indices = staff_area[staff_area.str.contains(target_norm, na=False)].index.tolist()
            
            if match_indices:
                idx = match_indices[0]
                my_shift = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
                others = df.drop([0, 1, idx, idx+1] if idx+1 < len(df) else [0, 1, idx]).copy().reset_index(drop=True)
                
                # 座標算出 (math.ceil適用)
                max_name_len = df.iloc[2:, 0].astype(str).apply(len).max()
                x_border = math.ceil(max(len(work_place_name), max_name_len))
                
                res[found_key] = {
                    "my_shift": my_shift,
                    "others": others,
                    "wp_name": work_place_name,
                    "drawing": {"x": x_border, "y": 10, "bottom": 20},
                    "header_date": df.iloc[0, :].tolist(),
                    "header_week": df.iloc[1, :].tolist()
                }
        return res
    finally:
        if os.path.exists(temp_name): os.remove(temp_name)
