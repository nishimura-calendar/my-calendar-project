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
            df = df.loc[:, (df != '').any(axis=0)] # 空列削除
            if df.empty: continue

            # --- 基準行（日付行）の動的特定 ---
            # 0列目から31列目までのどこかに「1」が含まれる最初の行を探す
            date_row_idx = -1
            for i in range(len(df)):
                row_str = "".join(df.iloc[i].astype(str))
                if "1" in row_str and "2" in row_str and "3" in row_str:
                    date_row_idx = i
                    break
            
            if date_row_idx == -1: continue # 日付行がない表はスキップ

            # 日付行(date_row)、曜日行(week_row)を特定
            week_row_idx = date_row_idx + 1
            if week_row_idx >= len(df): continue

            # --- 第一関門: 勤務地特定 (曜日行の0列目付近をチェック) ---
            header_text = normalize_text(str(df.iloc[week_row_idx, 0]))
            found_key = None
            work_place_name = "Unknown"
            for t_key, t_val in time_dic.items():
                if t_key in header_text:
                    found_key = t_key
                    work_place_name = t_val["original_name"]
                    break
            
            # もし見つからなければ日付行の0列目も探す（念のため）
            if not found_key:
                header_text_alt = normalize_text(str(df.iloc[date_row_idx, 0]))
                for t_key, t_val in time_dic.items():
                    if t_key in header_text_alt:
                        found_key = t_key
                        work_place_name = t_val["original_name"]
                        break
            
            if not found_key: continue

            # --- 第二関門: 整合性チェック ---
            pdf_days = re.sub(r'\D', '', str(df.iloc[date_row_idx, -1]))
            pdf_first_wd = str(df.iloc[week_row_idx, 1]).strip()
            
            if pdf_days != str(expected_info["days"]) or pdf_first_wd != expected_info["first_wd"]:
                return {"error": f"不一致：期待({expected_info['days']}/{expected_info['first_wd']}) PDF({pdf_days}/{pdf_first_wd})", "df": df}

            # --- 第三関門: スタッフ抽出 (曜日行の次から検索) ---
            target_norm = normalize_text(target_staff)
            staff_area = df.iloc[week_row_idx + 1:, 0].astype(str).apply(normalize_text)
            match_indices = staff_area[staff_area.str.contains(target_norm, na=False)].index.tolist()
            
            if match_indices:
                idx = match_indices[0]
                my_shift = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
                # 他スタッフ（日付行・曜日行・自分以外）
                others = df.drop([date_row_idx, week_row_idx, idx, idx+1] if idx+1 < len(df) else [date_row_idx, week_row_idx, idx]).copy().reset_index(drop=True)
                
                # 座標計算
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
