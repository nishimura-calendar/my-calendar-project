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
    # 空白、全角スペースを除去し、NFKC正規化後に小文字化
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def find_name_and_index_in_cell(target_name, cell_text):
    """
    【4/20 打ち合わせ準拠】
    セル内を改行で分割し、ターゲット名が含まれる要素のインデックス(offset)を返す。
    """
    if not cell_text: return False, 0
    clean_target = normalize_text(target_name)
    if not clean_target: return False, 0
    
    lines = str(cell_text).split('\n')
    for idx, line in enumerate(lines):
        clean_line = normalize_text(line)
        if clean_target in clean_line or clean_line in clean_target:
            return True, idx
    return False, 0

# --- 2. 時程表の取得 (ご提示の最新ロジック) ---
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
        
        full_df = pd.read_excel(fh, header=None, engine='openpyxl', sheet_name=0, dtype=str)
        
        location_rows = full_df[full_df.iloc[:, 0].notna()].index.tolist()
        location_data_dic = {}
        
        for i, start_row in enumerate(location_rows):
            end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
            location_name = str(full_df.iloc[start_row, 0]).strip()
            temp_range = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
            
            time_row = temp_range.iloc[0, :]
            first_num_col = None
            last_num_col = None
            
            for col_idx, val in enumerate(time_row):
                if col_idx < 1: continue
                try:
                    float(val)
                    if first_num_col is None: first_num_col = col_idx
                    last_num_col = col_idx
                except: continue
            
            if first_num_col is not None:
                start_col = max(1, first_num_col - 1)
                end_col = last_num_col + 1
                target_cols = [0, 1] + list(range(start_col, end_col))
                temp_range = temp_range.iloc[:, target_cols].copy()
                
                for col in range(len(temp_range.columns)):
                    if col < 2: continue
                    v = temp_range.iloc[0, col]
                    try:
                        f_v = float(v)
                        h = int(f_v)
                        m = int(round((f_v - h) * 60))
                        temp_range.iloc[0, col] = f"{h}:{m:02d}"
                    except: pass
            
            location_data_dic[location_name] = temp_range.fillna('')
            
        return location_data_dic
    except Exception as e:
        raise e

# --- 3. PDF解析 (A1セルの中心から勤務地を特定するロジック) ---
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
    
    # 決定された flavor: lattice と stream 両方試行
    for flavor in ['lattice', 'stream']:
        try:
            tables = camelot.read_pdf(temp_path, pages='all', flavor=flavor)
        except: continue
        
        for table in tables:
            df = table.df
            if df.empty: continue
            
            # 【絶対ルール】A1セルの改行分割から勤務地(T1/T2等)を特定
            header_lines = str(df.iloc[0, 0]).splitlines()
            work_place = header_lines[len(header_lines)//2] if header_lines else "Unknown"
            work_place = work_place.strip()

            for i in range(len(df)):
                cell_val = str(df.iloc[i, 0])
                # 名前の一致とセル内での行位置(offset)を取得
                found, offset = find_name_and_index_in_cell(target_staff, cell_val)
                
                if found:
                    my_daily = df.iloc[i : i + 2, :].copy().reset_index(drop=True)
                    others = df.copy().reset_index(drop=True)
                    # 後の処理のために名前+offsetを識別子として埋め込む
                    my_daily.iloc[0, 0] = f"{target_staff}_offset_{offset}"
                    pdf_results[work_place] = [my_daily, others]
                    break
        if pdf_results: break
                    
    return pdf_results, year, month

# --- 4. 統合と警告 ---
def integrate_with_warning(pdf_results, time_dic):
    integrated = {}
    for wp_key in pdf_results:
        if wp_key not in time_dic:
            st.error(f"{wp_key}という勤務地は登録されていません確認してください。")
            continue
        integrated[wp_key] = [pdf_results[wp_key][0], pdf_results[wp_key][1], time_dic[wp_key]]
    return integrated

# --- 5. 月間ループ ---
def process_full_month(integrated_dic, year, month):
    # CSVヘッダー
    final_rows = [["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location"]]
    if not year or not month: return final_rows
    
    _, last_day = calendar.monthrange(year, month)
    
    for day in range(1, last_day + 1):
        target_date = f"{year}/{month:02d}/{day:02d}"
        for place_key, data in integrated_dic.items():
            my_daily, others, time_sched = data[0], data[1], data[2]
            
            meta = str(my_daily.iloc[0, 0])
            offset = int(meta.split("_offset_")[-1]) if "_offset_" in meta else 0
            
            # 日付列の特定（PDFの構造上、1列目が名前、2列目が1日...となるケースが多いが、
            # Camelotの抽出結果に合わせて調整が必要。ここでは day 列目を参照）
            if day >= my_daily.shape[1]: continue
            
            raw_val = str(my_daily.iloc[0, day])
            val_lines = raw_val.split('\n')
            shift_text = val_lines[offset].strip() if offset < len(val_lines) else raw_val

            # シフト記号の抽出
            shifts = re.findall(r'[A-Z\d]+|[公有休特欠]', shift_text)
            for s_info in shifts:
                if any(k in s_info for k in ["公", "有", "休", "特", "欠"]):
                    final_rows.append([f"【{s_info}】", target_date, "", target_date, "", "True", "休暇", place_key])
                else:
                    # ここで consideration.py の詳細計算を呼び出す
                    import consideration as cons
                    # 引数構成: key, date, col_idx, s_info, my_df, other_df, time_df, results
                    try:
                        cons.shift_cal(place_key, target_date, day, s_info, my_daily, others, time_sched, final_rows)
                    except Exception as e:
                        st.warning(f"{target_date} {s_info} 解析スキップ: {e}")
                    
    return final_rows
