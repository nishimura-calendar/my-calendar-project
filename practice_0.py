import pandas as pd
import re
import unicodedata
import os
import camelot
import calendar
import math

def normalize_text(text):
    if not isinstance(text, str): return ""
    # 全角を半角、大文字を小文字に統一
    text = unicodedata.normalize('NFKC', text).lower()
    # スペース、改行、タブを削除
    return re.sub(r'[\s　\r\n\t]', '', text)

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
            df = table.df.replace(r'[\r\n]', '', regex=True)
            df = df.loc[:, (df != '').any(axis=0)]
            if df.empty or len(df) < 2: continue

            # 1. 日付行を特定
            date_row_idx = -1
            for i in range(min(5, len(df))):
                if "1" in df.iloc[i].astype(str).tolist():
                    date_row_idx = i
                    break
            if date_row_idx == -1: continue
            
            # 2. 曜日行を特定（日付行の次以降）
            week_row_idx = -1
            for i in range(date_row_idx, min(date_row_idx + 3, len(df))):
                row_str = "".join(df.iloc[i].astype(str))
                if any(w in row_str for w in ["月", "火", "水", "木", "金", "土", "日"]):
                    week_row_idx = i
                    break
            if week_row_idx == -1: week_row_idx = date_row_idx + 1

            # 3. 【西村様式】日付と曜日を除去して勤務地を特定
            # 日付行の周辺セルから情報を収集
            raw_header_text = "".join(df.iloc[date_row_idx:week_row_idx+1, 0:2].astype(str).values.flatten())
            
            # ① 数字(日付)を除去
            clean_text = re.sub(r'\d+', '', raw_header_text)
            # ② 曜日(月〜日)を除去
            clean_text = re.sub(r'[月火水木金土日]', '', clean_text)
            # ③ 正規化（小文字化、スペース削除）
            final_search_text = normalize_text(clean_text)
            
            found_key = None
            work_place_name = "Unknown"
            for t_key, t_val in time_dic.items():
                if t_key in final_search_text:
                    found_key = t_key
                    work_place_name = t_val["original_name"]
                    break
            
            if not found_key: continue

            # 4. 整合性チェック（日数のみ）
            pdf_days = re.sub(r'\D', '', str(df.iloc[date_row_idx, -1]))
            if pdf_days != str(expected_info["days"]): continue

            # 5. スタッフ抽出
            target_norm = normalize_text(target_staff)
            mask = df.apply(lambda row: row.astype(str).apply(normalize_text).str.contains(target_norm)).any(axis=1)
            match_indices = [idx for idx in df[mask].index.tolist() if idx > date_row_idx]
            
            if match_indices:
                idx = match_indices[0]
                my_shift = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
                others = df.drop([date_row_idx, week_row_idx, idx, idx+1] if idx+1 < len(df) else [date_row_idx, week_row_idx, idx]).copy().reset_index(drop=True)
                
                max_name_len = df.iloc[week_row_idx+1:, 0].astype(str).apply(len).max()
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
