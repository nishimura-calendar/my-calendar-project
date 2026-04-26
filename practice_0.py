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
        return {}

def pdf_reader(pdf_stream, target_staff, expected_info, time_dic):
    """PDF解析（全方位検索版）"""
    pdf_stream.seek(0)
    temp_name = "temp_process.pdf"
    with open(temp_name, "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    try:
        tables = camelot.read_pdf(temp_name, pages='all', flavor='lattice')
        res = {}
        for table in tables:
            df = table.df.replace(r'[\r\n]', '', regex=True)
            # 全て空の列を削除
            df = df.loc[:, (df != '').any(axis=0)]
            if df.empty: continue

            # --- 1. 日付行の動的特定（表全体から 1, 2, 3... を探す） ---
            date_row_idx = -1
            for i in range(len(df)):
                row_str = "".join(df.iloc[i].astype(str))
                # 「12345」のような並びがあるか確認
                if "1" in row_str and "2" in row_str and "3" in row_str:
                    date_row_idx = i
                    break
            if date_row_idx == -1: continue

            # 2. 曜日行は日付行のすぐ下と仮定
            week_row_idx = date_row_idx + 1
            if week_row_idx >= len(df): continue

            # --- 3. 勤務地特定の強化（日付・曜日行の全セルを合体） ---
            header_combined = normalize_text("".join(df.iloc[date_row_idx:week_row_idx+1].astype(str).values.flatten()))
            found_key = None
            work_place_name = "Unknown"
            for t_key, t_val in time_dic.items():
                if t_key in header_combined:
                    found_key = t_key
                    work_place_name = t_val["original_name"]
                    break
            
            if not found_key: continue

            # --- 4. 整合性チェック（日数のみ。曜日は多少のズレを許容してスキップ） ---
            pdf_days = re.sub(r'\D', '', str(df.iloc[date_row_idx, -1]))
            if pdf_days != str(expected_info["days"]):
                # 日数が合わない場合はそのページを飛ばす
                continue

            # --- 5. スタッフ抽出（全列検索） ---
            target_norm = normalize_text(target_staff)
            # 行のどこかに名前が含まれているインデックスを取得
            mask = df.apply(lambda row: row.astype(str).apply(normalize_text).str.contains(target_norm)).any(axis=1)
            match_indices = df[mask].index.tolist()
            
            # 曜日行より後の行に限定
            match_indices = [idx for idx in match_indices if idx > week_row_idx]
            
            if match_indices:
                idx = match_indices[0]
                # 自分の行とその次の行を抽出
                my_shift = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
                # 他のスタッフ
                others = df.drop([date_row_idx, week_row_idx, idx, idx+1] if idx+1 < len(df) else [date_row_idx, week_row_idx, idx]).copy().reset_index(drop=True)
                
                # デザイン座標算出（西村様指定のmath.ceil）
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
