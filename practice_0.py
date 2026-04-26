import pandas as pd
import re
import unicodedata
import os
import camelot
import calendar
import math

def normalize_text(text):
    if not isinstance(text, str): return ""
    # 1. 全角半角を統一し、小文字化
    text = unicodedata.normalize('NFKC', text).lower()
    # 2. 【重要】改行(\n)、空白、タブをすべて「空文字」に置換して消し去る
    text = re.sub(r'[\s　\r\n\t]', '', text)
    return text

def extract_year_month_from_text(text):
    if not text: return None
    text = unicodedata.normalize('NFKC', text)
    y_match = re.search(r'(\d{4})', text)
    m_match = re.search(r'(\d{1,2})月', text)
    if not y_match or not m_match: return None
    y_val, m_val = int(y_match.group(1)), int(m_match.group(1))
    first_wd_num, days_in_month = calendar.monthrange(y_val, m_val)
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    return {"year": y_val, "month": m_val, "days": days_in_month, "first_wd": weekdays_jp[first_wd_num]}

def time_schedule_from_drive(sheets_service, file_id):
    try:
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
                # 時程表側のKeyも改行なし・小文字・空白なしで保存
                norm_loc = normalize_text(str(loc))
                location_data_dic[norm_loc] = {
                    "df": df[df[first_col] == loc].fillna('').reset_index(drop=True),
                    "original_name": str(loc)
                }
        return location_data_dic
    except Exception: return {}

def pdf_reader(pdf_stream, target_staff, expected_info, time_dic):
    pdf_stream.seek(0)
    temp_name = "temp_process.pdf"
    with open(temp_name, "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    try:
        tables = camelot.read_pdf(temp_name, pages='all', flavor='lattice')
        res = {}
        for table in tables:
            df = table.df.copy()
            if df.empty or len(df) < 2: continue

            # 1. 「1」で始まるセルを特定（日付行の特定）
            date_row_idx = -1
            base_col_idx = -1
            for i in range(min(5, len(df))):
                for j in range(min(3, len(df.columns))):
                    val = normalize_text(str(df.iloc[i, j]))
                    if val.startswith('1'):
                        date_row_idx = i
                        base_col_idx = j
                        break
                if date_row_idx != -1: break
            
            if date_row_idx == -1: continue

            # 2. 【西村様式】日付・曜日・改行をすべて消去して判定
            raw_cell_text = str(df.iloc[date_row_idx, base_col_idx])
            
            # ① まず改行や空白を消す (normalize_textを利用)
            clean_text = normalize_text(raw_cell_text)
            # ② 数字(日付)をすべて消す
            clean_text = re.sub(r'\d+', '', clean_text)
            # ③ 曜日(月〜日)をすべて消す
            clean_text = re.sub(r'[月火水木金土日]', '', clean_text)
            
            # これで "1\n\nT2\n\n木" が "t2" だけになる
            found_key = None
            work_place_name = "Unknown"
            for t_key, t_val in time_dic.items():
                if t_key == clean_text or t_key in clean_text:
                    found_key = t_key
                    work_place_name = t_val["original_name"]
                    break
            
            if not found_key: continue

            # 曜日行は日付行と同じ
            week_row_idx = date_row_idx

            # 3. スタッフ抽出
            target_norm = normalize_text(target_staff)
            mask = df.apply(lambda row: row.astype(str).apply(normalize_text).str.contains(target_norm)).any(axis=1)
            match_indices = [idx for idx in df[mask].index.tolist() if idx > date_row_idx]
            
            if match_indices:
                idx = match_indices[0]
                my_shift = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
                others = df.drop([date_row_idx, week_row_idx, idx, idx+1] if idx+1 < len(df) else [date_row_idx, week_row_idx, idx]).copy().reset_index(drop=True)
                
                max_name_len = df.iloc[date_row_idx+1:, 0].astype(str).apply(len).max()
                x_border = math.ceil(max(len(work_place_name), max_name_len))
                
                res[found_key] = {
                    "my_shift": my_shift, "others": others, "wp_name": work_place_name,
                    "drawing": {"x": x_border, "y": 10, "bottom": 20},
                    "header_date": df.iloc[date_row_idx, :].tolist(),
                    "header_week": df.iloc[week_row_idx, :].tolist()
                }
        return res
    finally:
        if os.path.exists(temp_name): os.remove(temp_name)
