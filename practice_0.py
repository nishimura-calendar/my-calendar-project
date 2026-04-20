import pandas as pd
import camelot
import unicodedata
import re
import io
import calendar
import pdfplumber
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account

def get_gdrive_service(secrets):
    creds = service_account.Credentials.from_service_account_info(
        secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build('drive', 'v3', credentials=creds)

def normalize_text(text):
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def extract_year_month_from_text(text):
    if not text: return None, None
    text = unicodedata.normalize('NFKC', text)
    clean_text = re.sub(r'\s+', '', text)
    y_val, m_val = None, None
    month_match = re.search(r'(\d{1,2})月', clean_text)
    if month_match:
        m_val = int(month_match.group(1))
    nums = re.findall(r'\d+', clean_text)
    for n in nums:
        val = int(n)
        if len(n) == 4:
            y_val = val
        elif len(n) == 2:
            if m_val is None or (val != m_val):
                if y_val is None:
                    y_val = 2000 + val
    return y_val, m_val

def extract_max_day_from_pdf(pdf_stream):
    try:
        pdf_stream.seek(0)
        with pdfplumber.open(pdf_stream) as pdf:
            text = pdf.pages[0].extract_text()
            if not text: return None
            days = re.findall(r'\b(28|29|30|31)\b', text)
            if days: return int(max(days))
    except: pass
    return None

def extract_first_weekday_from_pdf(pdf_stream):
    try:
        pdf_stream.seek(0)
        with pdfplumber.open(pdf_stream) as pdf:
            text = pdf.pages[0].extract_text()
            if not text: return None
            match = re.search(r'\b1\s*[\(\（]([月火水木金土日])[\)\）]', text)
            if match: return match.group(1)
    except: pass
    return None

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
                is_numeric = any(char.isdigit() for char in val)
                is_summary = val in ["出勤", "退勤", "実働時間", "休憩時間", "深夜", "残業"]
                if is_numeric and not is_summary:
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
                        v = final_block.iloc[0, c]
                        try:
                            fv = float(v)
                            total_minutes = int(round(fv * 24 * 60)) if fv < 1.0 else int(fv)*60 + int(round((fv-int(fv))*60))
                            final_block.iloc[0, c] = f"{total_minutes//60}:{total_minutes%60:02d}"
                        except: pass
                location_data_dic[location_name] = final_block
        return location_data_dic
    except Exception as e:
        raise Exception(f"時程表構築エラー: {str(e)}")

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """
    【基本事項 7】引き継ぎ情報を抽出するロジック
    - t_col-1 を参照して「誰から引き継ぐか」
    - t_col+1 を参照して「誰に渡すか」を特定
    """
    num_cols = time_schedule.shape[1]
    # 自身のシフト詳細行を特定 (B列(1)がシフトコード)
    my_time_shift_rows = time_schedule[time_schedule.iloc[:, 1].astype(str) == shift_info]
    if my_time_shift_rows.empty:
        return
        
    # 終日イベントを追加
    final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "自動抽出", key])
    
    my_row = my_time_shift_rows.iloc[0]
    prev_val = ""
    
    # 3列目(index 3)以降が時間データ
    for t_col in range(3, num_cols):
        current_val = str(my_row[t_col]).strip()
        time_header = str(time_schedule.iloc[0, t_col]).strip()
        
        if current_val != prev_val:
            # 1. 前の予定の終了処理
            if prev_val != "" and final_rows and final_rows[-1][5] == "False":
                final_rows[-1][4] = time_header
                # 誰に渡すか（Taking over）を判定
                mask_next = (time_schedule.iloc[:, t_col].astype(str) == prev_val) & (time_schedule.iloc[:, 1] != shift_info)
                next_codes = time_schedule.loc[mask_next, time_schedule.columns[1]].tolist()
                
                # PDF(other_staff_shift)から該当日のシフトがnext_codesに含まれる人を探す
                next_staff_names = []
                for _, s_row in other_staff_shift.iterrows():
                    s_code = str(s_row.iloc[col]).strip()
                    if s_code in next_codes:
                        name = str(s_row.iloc[0]).split('\n')[0].strip()
                        next_staff_names.append(name)
                
                if next_staff_names:
                    final_rows[-1][0] += f" => to {'・'.join(next_staff_names)}"
                else:
                    # 交代相手がいない場合は休憩または退勤
                    is_after_work = all(str(my_row[k]).strip() == "" for k in range(t_col, num_cols))
                    final_rows[-1][0] += " => (退勤)" if is_after_work else ""

            # 2. 新しい予定の開始処理
            if current_val != "":
                # 誰から引き継ぐか（Handing over）を判定
                mask_prev = (time_schedule.iloc[:, t_col - 1].astype(str) == current_val) & (time_schedule.iloc[:, 1] != shift_info)
                prev_codes = time_schedule.loc[mask_prev, time_schedule.columns[1]].tolist()
                
                prev_staff_names = []
                for _, s_row in other_staff_shift.iterrows():
                    s_code = str(s_row.iloc[col]).strip()
                    if s_code in prev_codes:
                        name = str(s_row.iloc[0]).split('\n')[0].strip()
                        prev_staff_names.append(name)
                
                prefix = f"from {'・'.join(prev_staff_names)} " if prev_staff_names else ""
                subject = f"{prefix}【{current_val}】"
                final_rows.append([subject, target_date, time_header, target_date, "", "False", "自動抽出", key])
                
        prev_val = current_val

def pdf_reader(pdf_stream, target_staff):
    clean_target = normalize_text(target_staff)
    pdf_stream.seek(0)
    with open("temp.pdf", "wb") as f: f.write(pdf_stream.getbuffer())
    try:
        tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    except: return {}
    table_dictionary = {}
    for table in tables:
        df = table.df
        if not df.empty:
            header_lines = str(df.iloc[0, 0]).splitlines()
            # 勤務地の読み込みロジック (基本事項.docxの指示)
            target_idx = len(header_lines) // 2
            work_place = header_lines[target_idx] if target_idx < len(header_lines) else (header_lines[-1] if header_lines else "Unknown")
            
            search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
            matched_indices = df.index[search_col == clean_target].tolist()
            if matched_indices:
                idx = matched_indices[0]
                my_daily = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
                others = df.drop([0, idx, idx+1] if idx+1 < len(df) else [0, idx]).copy().reset_index(drop=True)
                table_dictionary[work_place] = [my_daily, others]
    return table_dictionary

def data_integration(pdf_dic, time_dic):
    integrated = {}
    for pk, pv in pdf_dic.items():
        match = next((k for k in time_dic.keys() if normalize_text(pk) in normalize_text(k)), None)
        if match: integrated[match] = pv + [time_dic[match]]
    return integrated, []

def process_full_month(integrated_dic, year, month):
    all_final_rows = []
    num_days = calendar.monthrange(year, month)[1]
    for day in range(1, num_days + 1):
        target_date_str = f"{year}-{month:02d}-{day:02d}"
        for place_key, data_list in integrated_dic.items():
            my_row, others, time_sched = data_list[0], data_list[1], data_list[2]
            if day + 1 >= my_row.shape[1]: continue
            val = str(my_row.iloc[0, day + 1])
            if not val or val.strip() == "" or val.lower() == 'nan': continue
            shifts = [s.strip() for s in re.split(r'[,、\s\n]+', val) if s.strip()]
            for s_info in shifts:
                shift_cal(place_key, target_date_str, day + 1, s_info, my_row, others, time_sched, all_final_rows)
    return all_final_rows
