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

# --- 2. 時程表の取得 (D列開始スキャンロジック) ---
def time_schedule_from_drive(service, file_id):
    """
    時程表スプレッドシートを解析。
    A=勤務地, B=シフト, C=ロッカー。D列(index 3)から数値スキャンを開始する。
    """
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
        
        # A列に値がある行（勤務地行）を特定
        location_rows = full_df[full_df.iloc[:, 0].notna()].index.tolist()
        location_data_dic = {}
        
        for i, start_row in enumerate(location_rows):
            end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
            location_name = str(full_df.iloc[start_row, 0]).strip()
            
            # その勤務地ブロックの抽出
            temp_range = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
            
            # --- 時間列のスタート特定 (D列から検索) ---
            time_row = temp_range.iloc[0, :]
            first_num_col = None
            last_num_col = None
            
            # ご指定通り、D列(インデックス3)からスキャンを開始
            for col_idx in range(len(time_row)):
                if col_idx < 3: continue # A, B, C列はスキップ
                
                val = time_row[col_idx]
                try:
                    # 数値(float)として解釈可能かチェック
                    f_val = float(val)
                    if first_num_col is None:
                        first_num_col = col_idx
                    last_num_col = col_idx
                    
                    # 内部表示用に "6:15" などの形式に変換
                    h = int(f_val)
                    m = int(round((f_val - h) * 60))
                    temp_range.iloc[0, col_idx] = f"{h}:{m:02d}"
                except (ValueError, TypeError):
                    continue
            
            # 抽出範囲の確定
            if first_num_col is not None:
                # A(0), B(1), C(2) 列と、見つかった時間列以降を結合
                target_cols = [0, 1, 2] + list(range(first_num_col, last_num_col + 1))
                temp_range = temp_range.iloc[:, target_cols].copy()
            
            # Streamlit表示エラー回避
            temp_range.columns = range(len(temp_range.columns))
            location_data_dic[location_name] = temp_range.fillna('')
            
        return location_data_dic
    except Exception as e:
        raise e

# --- 3. PDF解析 ---
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
                
                header_lines = str(df.iloc[0, 0]).splitlines()
                work_place = header_lines[len(header_lines)//2] if header_lines else "Unknown"
                work_place = work_place.strip()

                for i in range(len(df)):
                    cell_val = str(df.iloc[i, 0])
                    found, offset = find_name_and_index_in_cell(target_staff, cell_val)
                    if found:
                        my_daily = df.iloc[i : i + 2, :].copy()
                        my_daily.columns = range(len(my_daily.columns))
                        my_daily = my_daily.reset_index(drop=True)
                        
                        others = df.copy()
                        others.columns = range(len(others.columns))
                        others = others.reset_index(drop=True)
                        
                        my_daily.iloc[0, 0] = f"{target_staff}_offset_{offset}"
                        pdf_results[work_place] = [my_daily, others]
                        break
            if pdf_results: break
        except: continue
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
            
            if day >= my_daily.shape[1]: continue
            
            raw_val = str(my_daily.iloc[0, day])
            val_lines = raw_val.split('\n')
            shift_text = val_lines[offset].strip() if offset < len(val_lines) else raw_val

            shifts = re.findall(r'[A-Z\d]+|[公有休特欠]', shift_text)
            for s_info in shifts:
                if any(k in s_info for k in ["公", "有", "休", "特", "欠"]):
                    final_rows.append([f"【{s_info}】", target_date, "", target_date, "", "True", "休暇", place_key])
                else:
                    import consideration as cons
                    try:
                        cons.shift_cal(place_key, target_date, day, s_info, my_daily, others, time_sched, final_rows)
                    except: pass
    return final_rows
