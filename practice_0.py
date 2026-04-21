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
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def find_name_and_index_in_cell(target_name, cell_text):
    """
    セル内改行を考慮した名前一致確認と、その行番号(offset)の取得
    """
    if not cell_text: return False, 0
    clean_target = normalize_text(target_name)
    if not clean_target: return False, 0
    lines = str(cell_text).split('\n')
    for idx, line in enumerate(lines):
        if clean_target in normalize_text(line):
            return True, idx
    return False, 0

# --- 2. 時程表の取得 ---
def time_schedule_from_drive(service, file_id):
    try:
        file_metadata = service.files().get(fileId=file_id, fields='mimeType').execute()
        request = service.files().get_media(fileId=file_id)
        if file_metadata.get('mimeType') == 'application/vnd.google-apps.spreadsheet':
            request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done: _, done = downloader.next_chunk()
        fh.seek(0)
        
        full_df = pd.read_excel(fh, header=None, engine='openpyxl', dtype=str)
        location_rows = full_df[full_df.iloc[:, 0].notna()].index.tolist()
        location_data_dic = {}
        
        for i, start_row in enumerate(location_rows):
            end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
            location_name = str(full_df.iloc[start_row, 0]).strip()
            temp_range = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
            
            time_row = temp_range.iloc[0, :]
            first_num_col = None
            last_num_col = None
            for col_idx in range(len(time_row)):
                if col_idx < 3: continue 
                val = time_row[col_idx]
                try:
                    f_val = float(val)
                    if first_num_col is None: first_num_col = col_idx
                    last_num_col = col_idx
                    h = int(f_val)
                    m = int(round((f_val - h) * 60))
                    temp_range.iloc[0, col_idx] = f"{h}:{m:02d}"
                except: continue
            
            if first_num_col is not None:
                target_cols = [0, 1, 2] + list(range(first_num_col, last_num_col + 1))
                temp_range = temp_range.iloc[:, target_cols].copy()
            
            temp_range.columns = range(len(temp_range.columns))
            location_data_dic[location_name] = temp_range.fillna('')
            
        return location_data_dic
    except Exception as e:
        raise e

# --- 3. PDF解析（修正：自分を除外、日付行を除外） ---
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
    for flavor in ['lattice', 'stream']:
        try:
            tables = camelot.read_pdf(temp_path, pages='all', flavor=flavor)
            for table in tables:
                df = table.df
                if df.empty: continue
                
                # A1セルのテキストから勤務地(T1/T2等)を推測
                header_text = str(df.iloc[0, 0])
                header_lines = header_text.splitlines()
                work_place = "Unknown"
                for line in header_lines:
                    if "T1" in line.upper(): work_place = "T1"; break
                    if "T2" in line.upper(): work_place = "T2"; break
                
                # スタッフ行の特定
                target_row_idx = -1
                target_offset = 0
                for i in range(len(df)):
                    cell_val = str(df.iloc[i, 0])
                    found, offset = find_name_and_index_in_cell(target_staff, cell_val)
                    if found:
                        target_row_idx = i
                        target_offset = offset
                        break
                
                if target_row_idx != -1:
                    # 自分のシフトデータ（2行分）
                    my_daily = df.iloc[target_row_idx : target_row_idx + 2, :].copy()
                    my_daily.columns = range(len(my_daily.columns))
                    my_daily = my_daily.reset_index(drop=True)
                    my_daily.iloc[0, 0] = f"{target_staff}_offset_{target_offset}"

                    # 他スタッフのデータ構築（修正ポイント）
                    # 1. ヘッダー（日付・曜日行）を除外するために、数値や曜日の列が多い行を特定して捨てる
                    cleaned_others = []
                    for i in range(len(df)):
                        # 自分の行(target_row_idx)と、その下の記号行(target_row_idx+1)は除外
                        if i == target_row_idx or i == target_row_idx + 1:
                            continue
                        
                        row_head = str(df.iloc[i, 0])
                        # 数値(1 2 3...)や曜日(日 月 火...)のみの行、または空の行はスタッフ行ではないとみなして除外
                        if not row_head.strip(): continue
                        if re.match(r'^[\d\s]+$', row_head.replace('\n', '')): continue # 日付のみ行
                        if any(day in row_head for day in ["日", "月", "火", "水", "木", "金", "土"]):
                            # 名前が含まれていない曜日行をスキップ
                            if len(row_head.strip()) <= 2: continue
                        
                        cleaned_others.append(df.iloc[i, :])
                    
                    others = pd.DataFrame(cleaned_others)
                    others.columns = range(len(others.columns))
                    others = others.reset_index(drop=True)
                    
                    pdf_results[work_place] = [my_daily, others]
                    break
            if pdf_results: break
        except Exception as e:
            continue
    return pdf_results, year, month

# --- 4. 統合 ---
def integrate_with_warning(pdf_results, time_dic):
    integrated = {}
    for wp_key in pdf_results:
        if wp_key not in time_dic:
            st.error(f"警告: 時程表に勤務地 '{wp_key}' が登録されていません。")
            continue
        integrated[wp_key] = [pdf_results[wp_key][0], pdf_results[wp_key][1], time_dic[wp_key]]
    return integrated

# --- 5. メインループ ---
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
            
            # PDF上の日付列を特定 (3列目以降を想定)
            # Camelotのパース結果により列位置がズレるため、柔軟に対応
            found_col = -1
            for col in range(2, my_daily.shape[1]):
                col_head = str(my_daily.iloc[0, col])
                if str(day) in col_head.replace('\n', ' '):
                    found_col = col
                    break
            
            if found_col == -1: continue
            
            raw_val = str(my_daily.iloc[0, found_col])
            val_lines = raw_val.split('\n')
            shift_text = val_lines[offset].strip() if offset < len(val_lines) else raw_val

            shifts = re.findall(r'[A-Z\d]+|[公有休特欠]', shift_text)
            for s_info in shifts:
                if any(k in s_info for k in ["公", "有", "休", "特", "欠"]):
                    final_rows.append([f"【{s_info}】", target_date, "", target_date, "", "True", "休暇", place_key])
                else:
                    import consideration as cons
                    try:
                        cons.shift_cal(place_key, target_date, found_col, s_info, my_daily, others, time_sched, final_rows)
                    except: pass
    return final_rows
