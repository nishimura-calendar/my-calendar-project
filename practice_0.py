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
    if not text: return None
    text = unicodedata.normalize('NFKC', text)
    y_match = re.search(r'(\d{4})', text)
    m_match = re.search(r'(\d{1,2})月', text)
    if not y_match or not m_match: return None
    y_val, m_val = int(y_match.group(1)), int(m_match.group(1))
    first_wd_num, days_in_month = calendar.monthrange(y_val, m_val)
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    return {"year": y_val, "month": m_val, "days": days_in_month, "first_wd": weekdays_jp[first_wd_num]}

# --- app.py から呼び出される重要な関数 ---
def time_schedule_from_drive(sheets_service, file_id):
    """時程表(正)の読み込み"""
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
            # A列（勤務地）の空欄を埋める
            df[first_col] = df[first_col].replace('', None).ffill()
            
            for loc in df[first_col].unique():
                if not loc: continue
                norm_loc = normalize_text(str(loc))
                location_data_dic[norm_loc] = {
                    "df": df[df[first_col] == loc].fillna('').reset_index(drop=True),
                    "original_name": str(loc)
                }
        return location_data_dic
    except Exception as e:
        print(f"Error in time_schedule_from_drive: {e}")
        return {}

def pdf_reader(pdf_stream, target_staff, expected_info, time_dic):
    """PDF解析（動的座標特定）"""
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
            if df.empty: continue

            # 日付行（1, 2, 3...が含まれる行）を検索
            date_row_idx = -1
            for i in range(min(5, len(df))): # 最初の5行以内を探索
                row_vals = df.iloc[i].astype(str).tolist()
                if "1" in row_vals and "2" in row_vals:
                    date_row_idx = i
                    break
            
            if date_row_idx == -1: continue

            week_row_idx = date_row_idx + 1
            if week_row_idx >= len(df): continue

            # 勤務地特定
            header_text = normalize_text(str(df.iloc[week_row_idx, 0]) + str(df.iloc[date_row_idx, 0]))
            found_key = None
            work_place_name = "Unknown"
            for t_key, t_val in time_dic.items():
                if t_key in header_text:
                    found_key = t_key
                    work_place_name = t_val["original_name"]
                    break
            
            if not found_key: continue

            # 整合性チェック
            pdf_days = re.sub(r'\D', '', str(df.iloc[date_row_idx, -1]))
            pdf_first_wd = str(df.iloc[week_row_idx, 1]).strip()
            if pdf_days != str(expected_info["days"]) or pdf_first_wd != expected_info["first_wd"]:
                return {"error": f"不一致：期待({expected_info['days']}/{expected_info['first_wd']}) PDF({pdf_days}/{pdf_first_wd})", "df": df}

            # スタッフ抽出
            target_norm = normalize_text(target_staff)
            staff_area = df.iloc[week_row_idx + 1:, 0].astype(str).apply(normalize_text)
            match_indices = staff_area[staff_area.str.contains(target_norm, na=False)].index.tolist()
            
            if match_indices:
                idx = match_indices[0]
                my_shift = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
                others = df.drop([date_row_idx, week_row_idx, idx, idx+1] if idx+1 < len(df) else [date_row_idx, week_row_idx, idx]).copy().reset_index(drop=True)
                
                # 座標算出
                max_name_len = df.iloc[week_row_idx+1:, 0].astype(str).apply(len).max()
                x_border = math.ceil(max(len(work_place_name), max_name_len))
                
                res[found_key] = {
                    "my_shift": my_shift, "others": others, "wp_name": work_place_name,
                    "drawing": {"x": x_border, "y": math.ceil(10.0), "bottom": math.ceil(20.0)},
                    "header_date": df.iloc[date_row_idx, :].tolist(),
                    "header_week": df.iloc[week_row_idx, :].tolist()
                }
        return res
    finally:
        if os.path.exists(temp_name): os.remove(temp_name)
