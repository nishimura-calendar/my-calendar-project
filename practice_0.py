import pandas as pd
import camelot
import unicodedata
import re
import io
import calendar
import pdfplumber
import datetime
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account

# --- app.py から呼び出されるユーティリティ関数 ---

def extract_year_month_from_text(text):
    if not text: return None, None
    text = unicodedata.normalize('NFKC', text)
    year_match = re.search(r'(202\d)', text)
    month_match = re.search(r'(\d{1,2})月', text)
    y = int(year_match.group(1)) if year_match else datetime.datetime.now().year
    m = int(month_match.group(1)) if month_match else None
    return y, m

def extract_max_day_from_pdf(pdf_stream):
    pdf_stream.seek(0)
    with pdfplumber.open(pdf_stream) as pdf:
        text = pdf.pages[0].extract_text() or ""
        days = re.findall(r'\b([1-3][0-9]|[1-9])\b', text)
        valid_days = [int(d) for d in days if 1 <= int(d) <= 31]
        return max(valid_days) if valid_days else 31

def extract_first_weekday_from_pdf(pdf_stream):
    pdf_stream.seek(0)
    with pdfplumber.open(pdf_stream) as pdf:
        page_text = pdf.pages[0].extract_text() or ""
        match = re.search(r'1\s*\(?([月火水木金土日])\)?', page_text)
        return match.group(1) if match else None

# --- 内部計算用 ---

def convert_float_to_time(val):
    try:
        f_val = float(val)
        hours = int(f_val)
        minutes = int(round((f_val - hours) * 60))
        if minutes >= 60:
            hours += 1
            minutes = 0
        return f"{hours:02d}:{minutes:02d}"
    except:
        return str(val)

def normalize_text(text):
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

# --- メインロジック ---

def get_gdrive_service(secrets):
    creds = service_account.Credentials.from_service_account_info(
        secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build('drive', 'v3', credentials=creds)

def pdf_reader(pdf_stream, target_staff):
    """
    基本事項に準拠し、iloc(0,0)から勤務地を特定。
    ターゲットのシフト行を正確に抽出する。
    """
    clean_target = normalize_text(target_staff)
    pdf_stream.seek(0)
    # 一時ファイルとして保存（Camelot用）
    with open("temp.pdf", "wb") as f: f.write(pdf_stream.getbuffer())
    
    try:
        tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    except: return {}
    
    table_dictionary = {}
    for table in tables:
        df = table.df
        if df.empty: continue
        
        # 基本事項：iloc(0,0) の中央値から勤務地名を特定
        text = str(df.iloc[0, 0])
        lines = text.splitlines()
        target_index = text.count('\n') // 2
        work_place = lines[target_index].strip() if target_index < len(lines) else (lines[-1].strip() if lines else "Unknown")
        
        # ターゲットスタッフを探索
        search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
        matched_indices = df.index[search_col.str.contains(clean_target)].tolist()
        
        if matched_indices:
            idx = matched_indices[0]
            # 自分の行（名前＋シフト記号の2行分を保持）
            my_daily = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
            # 他のスタッフ（交代相手検索用：ヘッダーと自分以外）
            others = df.drop([idx, idx+1] if idx+1 < len(df) else [idx]).copy().reset_index(drop=True)
            
            table_dictionary[work_place] = [my_daily, others]
            
    return table_dictionary

def time_schedule_from_drive(service, file_id):
    try:
        request = service.files().get_media(fileId=file_id)
        file_metadata = service.files().get(fileId=file_id, fields='mimeType').execute()
        if file_metadata.get('mimeType') == 'application/vnd.google-apps.spreadsheet':
            request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done: _, done = downloader.next_chunk()
        fh.seek(0)
        
        full_df = pd.read_excel(fh, header=None, engine='openpyxl', sheet_name=0, dtype=str).fillna('')
        location_rows = full_df[full_df.iloc[:, 0].str.strip() != ''].index.tolist()
        location_data_dic = {}
        
        for i, start_row in enumerate(location_rows):
            next_start = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
            temp_range = full_df.iloc[start_row:next_start, :].copy().reset_index(drop=True)
            location_name = temp_range.iloc[0, 0].strip()
            
            header_row = temp_range.iloc[0]
            start_col, last_col = None, None
            for c in range(1, len(header_row)):
                val = str(header_row[c]).strip()
                if any(char.isdigit() for char in val):
                    if start_col is None: start_col = c
                    last_col = c
                elif start_col is not None: break
            
            if start_col is not None:
                base_indices = [0, 1, 2]
                time_indices = list(range(start_col, last_col + 1))
                all_indices = sorted(list(set(base_indices + time_indices)))
                final_block = temp_range.iloc[:, all_indices].copy().reset_index(drop=True)
                for c in range(len(final_block.columns)):
                    if all_indices[c] in time_indices:
                        final_block.iloc[0, c] = convert_float_to_time(final_block.iloc[0, c])
                location_data_dic[location_name] = final_block
        return location_data_dic
    except Exception as e:
        raise Exception(f"時程表読込エラー: {str(e)}")

def shift_cal(key, target_date, col, shift_info, other_staff_shift, time_schedule, final_rows):
    if time_schedule is None: return
    ts = time_schedule.fillna("").astype(str)
    
    # シフト記号が一致する行を特定
    my_rows = ts[ts.iloc[:, 1].apply(lambda x: shift_info == x or shift_info in x)]
    if my_rows.empty: return
    
    my_row = my_rows.iloc[0]
    num_cols = ts.shape[1]
    prev_val = ""
    
    for t_col in range(3, num_cols):
        current_val = my_row[t_col].strip()
        time_header = ts.iloc[0, t_col].strip()
        
        if current_val != prev_val:
            if prev_val != "" and final_rows and final_rows[-1][5] == "False":
                final_rows[-1][4] = time_header
                mask_next = (ts.iloc[:, t_col] == prev_val) & (ts.iloc[:, 1] != shift_info)
                next_codes = ts.loc[mask_next, ts.columns[1]].tolist()
                next_staff = []
                for _, s_row in other_staff_shift.iterrows():
                    if col < len(s_row) and any(c in str(s_row.iloc[col]) for c in next_codes):
                        n = str(s_row.iloc[0]).splitlines()[0].strip()
                        if n and n.lower() != 'nan': next_staff.append(n)
                if next_staff:
                    final_rows[-1][0] += f" => to {'・'.join(sorted(list(set(next_staff))))}"
                elif all(my_row[k].strip() == "" for k in range(t_col, num_cols)):
                    final_rows[-1][0] += " => (退勤)"

            if current_val != "":
                mask_prev = (ts.iloc[:, t_col - 1] == current_val) & (ts.iloc[:, 1] != shift_info)
                prev_codes = ts.loc[mask_prev, ts.columns[1]].tolist()
                prev_staff = []
                for _, s_row in other_staff_shift.iterrows():
                    if col < len(s_row) and any(c in str(s_row.iloc[col]) for c in prev_codes):
                        n = str(s_row.iloc[0]).splitlines()[0].strip()
                        if n and n.lower() != 'nan': prev_staff.append(n)
                from_str = f"from {'・'.join(sorted(list(set(prev_staff))))} " if prev_staff else ""
                subject = f"{from_str}【{current_val}】"
                final_rows.append([subject, target_date, time_header, target_date, "", "False", "詳細スケジュール", key])
        prev_val = current_val

def process_full_month(integrated_dic, year, month):
    all_final_rows = []
    num_days = calendar.monthrange(year, month)[1]
    
    for day in range(1, num_days + 1):
        target_date_str = f"{year}-{month:02d}-{day:02d}"
        
        for place_key, data_list in integrated_dic.items():
            my_daily, others = data_list[0], data_list[1]
            time_sched = data_list[2] if len(data_list) > 2 else None
            
            # --- 修正：1日がどの列にあるかを動的に判定 ---
            col_idx = -1
            # 1行目または2行目から「1」という単独の数字を探す
            for r in range(min(2, len(my_daily))):
                for c in range(1, len(my_daily.columns)):
                    cell_val = str(my_daily.iloc[r, c]).replace('\n', '').strip()
                    if cell_val == "1" or cell_val == "01":
                        col_idx = c + (day - 1)
                        break
                if col_idx != -1: break
            
            if col_idx == -1 or col_idx >= my_daily.shape[1]:
                continue
            
            # シフト情報の取得（記号行から優先的に取得）
            # 1行目が日付、2行目が記号のパターンが多いため
            raw_val = ""
            for r in range(len(my_daily)):
                v = str(my_daily.iloc[r, col_idx]).strip()
                if v and not v.isdigit() and v.lower() != 'nan':
                    raw_val = v
                    break
            
            if not raw_val: continue
            
            shifts = [s.strip() for s in re.split(r'[,、\s\n]+', raw_val) if s.strip()]
            for s_info in shifts:
                if any(k in s_info for k in ["休", "公", "有", "有給", "特", "欠", "振", "替"]):
                    all_final_rows.append([f"【{s_info}】", target_date_str, "", target_date_str, "", "True", "休暇等", place_key])
                    continue
                
                all_final_rows.append([f"{place_key}_{s_info}", target_date_str, "", target_date_str, "", "True", "勤務予定", place_key])
                if time_sched is not None:
                    shift_cal(place_key, target_date_str, col_idx, s_info, others, time_sched, all_final_rows)
                    
    return all_final_rows

def data_integration(pdf_dic, time_dic):
    integrated = {}
    for pk, pv in pdf_dic.items():
        # 紐付け用キーの正規化比較
        match = next((k for k in time_dic.keys() if normalize_text(pk) in normalize_text(k)), None)
        if match:
            integrated[match] = pv + [time_dic[match]]
        else:
            # 時程表がない場合もデータを保持
            integrated[pk] = pv
    return integrated, []
