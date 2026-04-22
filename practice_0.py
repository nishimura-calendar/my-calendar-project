import pandas as pd
import camelot
import unicodedata
import re
import io
import calendar
import streamlit as st
from googleapiclient.http import MediaIoBaseDownload

# --- 1. テキストの正規化 ---
def normalize_text(text):
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　\n]', '', unicodedata.normalize('NFKC', text)).lower()

def find_name_and_index_in_cell(target_name, cell_text):
    if not cell_text: return False, 0
    clean_target = normalize_text(target_name)
    lines = str(cell_text).split('\n')
    for idx, line in enumerate(lines):
        if clean_target in normalize_text(line):
            return True, idx
    return False, 0

# --- 2. 時程表の取得 ---
def time_schedule_from_drive(service, file_id):
    try:
        request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done: _, done = downloader.next_chunk()
        fh.seek(0)
        
        full_dict = pd.read_excel(fh, sheet_name=None, header=None, engine='openpyxl', dtype=str)
        location_data_dic = {}
        
        for sheet_name, df in full_dict.items():
            location_name = sheet_name.strip()
            time_row = df.iloc[0, :]
            first_num_col = None
            last_num_col = None
            for col_idx in range(len(time_row)):
                if col_idx < 3: continue 
                val = time_row[col_idx]
                try:
                    f_val = float(val)
                    if first_num_col is None: first_num_col = col_idx
                    last_num_col = col_idx
                    h = int(f_val * 24) % 24 if f_val < 1 else int(f_val)
                    m = int(round((f_val * 24 - int(f_val * 24)) * 60)) if f_val < 1 else 0
                    df.iloc[0, col_idx] = f"{h}:{m:02d}"
                except:
                    if ":" in str(val):
                        if first_num_col is None: first_num_col = col_idx
                        last_num_col = col_idx
                    continue
            
            if first_num_col is not None:
                target_cols = [0, 1, 2] + list(range(first_num_col, last_num_col + 1))
                df = df.iloc[:, target_cols].copy()
            
            df.columns = range(len(df.columns))
            location_data_dic[location_name] = df.fillna('')
            
        return location_data_dic
    except Exception as e:
        raise e

# --- 3. 整合性チェック ---
def check_calendar_consistency(df, year, month):
    """
    PDF内の日数と1日の曜日が、カレンダー理論値と一致するか確認する
    """
    if not year or not month:
        return False, "ファイル名から年・月を特定できませんでした。"

    # カレンダー上の情報
    _, last_day_theory = calendar.monthrange(year, month)
    first_weekday_theory = calendar.weekday(year, month, 1) # 0=Mon, 6=Sun
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    theory_wd_str = weekdays_jp[first_weekday_theory]

    # PDF上の情報 (1行目付近から探索)
    pdf_days = []
    pdf_first_wd = ""
    
    # 最初の数行から数字(日付)と曜日を探す
    found_1st = False
    for col in range(1, df.shape[1]):
        cell = str(df.iloc[0, col])
        # 日付の抽出
        day_match = re.search(r'(\d+)', cell)
        if day_match:
            d_val = int(day_match.group(1))
            pdf_days.append(d_val)
            # 1日の曜日を特定
            if d_val == 1 and not found_1st:
                for wd in weekdays_jp:
                    if wd in cell:
                        pdf_first_wd = wd
                        found_1st = True

    pdf_last_day = max(pdf_days) if pdf_days else 0
    
    errors = []
    if pdf_last_day != last_day_theory:
        errors.append(f"末日が一致しません（理論値: {last_day_theory}日 / PDF検出: {pdf_last_day}日）")
    if pdf_first_wd and pdf_first_wd != theory_wd_str:
        errors.append(f"1日の曜日が一致しません（理論値: {theory_wd_str} / PDF検出: {pdf_first_wd}）")

    if errors:
        return False, "、".join(errors)
    return True, ""

# --- 4. 交代（打ち合わせ）ロジック ---
def shift_cal(key, target_date, pdf_col, shift_info, other_staff_shift, time_schedule, final_rows):
    clean_shift_info = normalize_text(shift_info)
    my_time_indices = [idx for idx, val in enumerate(time_schedule.iloc[:, 1]) if normalize_text(str(val)) == clean_shift_info]
    
    if not my_time_indices:
        return

    my_time_shift = time_schedule.iloc[my_time_indices[0]:my_time_indices[0]+1, :]
    prev_val = ""
    for t_col in range(2, time_schedule.shape[1]):
        current_val = str(my_time_shift.iloc[0, t_col]).strip()
        if current_val.lower() in ['nan', 'none']: current_val = ""

        if current_val != prev_val:
            if current_val != "":
                mask_h = (time_schedule.iloc[:, t_col].astype(str) == prev_val) & (time_schedule.iloc[:, 1].astype(str) != shift_info)
                mask_t = (time_schedule.iloc[:, t_col].astype(str) == current_val) & (time_schedule.iloc[:, 1].astype(str) != shift_info)
                
                res = ["", ""]
                for i, mask in enumerate([mask_h, mask_t]):
                    codes = [normalize_text(str(c)) for c in time_schedule.loc[mask, 1]]
                    matched = []
                    for _, s_row in other_staff_shift.iterrows():
                        if normalize_text(str(s_row.iloc[pdf_col])) in codes:
                            name = str(s_row.iloc[0]).split('\n')[0].strip()
                            if name: matched.append(name)
                    res[i] = "・".join(matched)

                h_str = f"to {res[0]}" if res[0] else ""
                t_str = f"【{current_val}】from {res[1]}" if res[1] else f"【{current_val}】"
                subject = f"{h_str} => {t_str}".strip(" => ")
                start_t = str(time_schedule.iloc[0, t_col])
                final_rows.append([subject, target_date, start_t, target_date, "", "False", "", key])
            else:
                if final_rows and final_rows[-1][5] == "False":
                    final_rows[-1][4] = str(time_schedule.iloc[0, t_col])
            prev_val = current_val

# --- 5. PDF解析 ---
def pdf_reader(pdf_stream, target_staff, file_name=""):
    pdf_stream.seek(0)
    year, month = None, None
    nums = re.findall(r'\d+', normalize_text(file_name))
    for n in nums:
        if len(n) == 4: year = int(n)
        if len(n) <= 2: month = int(n)

    temp_path = "temp_process.pdf"
    with open(temp_path, "wb") as f: f.write(pdf_stream.getbuffer())
    
    pdf_results = {}
    consistency_report = {} # 不一致情報を格納

    for flavor in ['lattice', 'stream']:
        try:
            tables = camelot.read_pdf(temp_path, pages='all', flavor=flavor)
            for table in tables:
                df = table.df
                if df.empty: continue
                
                # --- 勤務地特定ロジックの固定 ---
                header = re.findall(r'[\u4E00-\u9FD5a-zA-Z0-9]+', str(df.iloc[0, 0]))
                work_place = header[len(header)//2] if header else "Unknown"
                
                # --- カレンダー整合性チェック ---
                is_ok, reason = check_calendar_consistency(df, year, month)
                if not is_ok:
                    consistency_report[work_place] = {"reason": reason, "df": df}
                    continue # 不一致ならこのテーブルはスキップ（後で報告）

                # 自分を探す
                target_row_idx = -1
                target_offset = 0
                for i in range(len(df)):
                    found, offset = find_name_and_index_in_cell(target_staff, df.iloc[i, 0])
                    if found:
                        target_row_idx = i
                        target_offset = offset
                        break
                
                if target_row_idx != -1:
                    my_daily = df.iloc[target_row_idx : target_row_idx + 2, :].copy()
                    my_daily.columns = range(len(my_daily.columns))
                    my_daily = my_daily.reset_index(drop=True)
                    my_daily.iloc[0, 0] = f"{target_staff}_offset_{target_offset}"

                    others = []
                    for i in range(len(df)):
                        if i in [target_row_idx, target_row_idx + 1]: continue
                        row_head = str(df.iloc[i, 0]).strip()
                        if not row_head or any(k in row_head for k in ["勤務予定表", "T1", "T2"]): continue
                        # 日付行・曜日行除外
                        just_nums = re.sub(r'[\s\n　]', '', row_head)
                        if just_nums.isdigit() and len(just_nums) > 5: continue
                        if any(wd in row_head for wd in ["日", "月", "火", "水", "木", "金", "土"]) and len(row_head) < 5: continue
                        others.append(df.iloc[i, :])
                    
                    pdf_results[work_place] = [my_daily, pd.DataFrame(others).reset_index(drop=True)]
                    break
            if pdf_results: break
        except Exception:
            continue
            
    return pdf_results, year, month, consistency_report

# --- 6. メイン統合 ---
def process_full_month(integrated_dic, year, month):
    final_rows = [["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location"]]
    if not year or not month: return final_rows
    _, last_day = calendar.monthrange(year, month)
    
    for day in range(1, last_day + 1):
        target_date = f"{year}/{month:02d}/{day:02d}"
        for place_key, data in integrated_dic.items():
            my_daily, others, time_sched = data[0], data[1], data[2]
            meta = str(my_daily.iloc[0, 0])
            offset = int(meta.split("_offset_")[-1]) if "_offset_" in meta else 0
            
            f_col = -1
            for col in range(1, my_daily.shape[1]):
                if re.search(rf'\b{day}\b', str(my_daily.iloc[0, col])):
                    f_col = col
                    break
            if f_col == -1: continue
            
            raw_val = str(my_daily.iloc[0, f_col])
            val_lines = raw_val.split('\n')
            shift_text = val_lines[offset].strip() if offset < len(val_lines) else raw_val

            shifts = re.findall(r'[A-Z\d]+|[公有休特欠]', shift_text)
            for s_info in shifts:
                if any(k in s_info for k in ["公", "有", "休", "特", "欠"]):
                    final_rows.append([f"【{s_info}】", target_date, "", target_date, "", "True", "休暇", place_key])
                else:
                    final_rows.append([f"{place_key}_{s_info}", target_date, "", target_date, "", "True", "", place_key])
                    shift_cal(place_key, target_date, f_col, s_info, others, time_sched, final_rows)
    return final_rows
