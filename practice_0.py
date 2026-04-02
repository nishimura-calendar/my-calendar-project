import pandas as pd
import pdfplumber
import unicodedata
import re
import io
import calendar
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account

def get_gdrive_service(secrets):
    creds = service_account.Credentials.from_service_account_info(
        secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build('drive', 'v3', credentials=creds)

def time_schedule_from_drive(service, file_id):
    try:
        file_metadata = service.files().get(fileId=file_id, fields='mimeType').execute()
        mime_type = file_metadata.get('mimeType')
        if mime_type == 'application/vnd.google-apps.spreadsheet':
            request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        else:
            request = service.files().get_media(fileId=file_id)
        
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        
        fh.seek(0)
        all_sheets = pd.read_excel(fh, sheet_name=None, header=None)
        
        time_dic = {}
        for sheet_name, df in all_sheets.items():
            df = df.fillna("")
            def clean_format(x):
                s = str(x)
                return s[:-2] if s.endswith('.0') else s
            if hasattr(df, 'map'):
                df = df.map(clean_format)
            else:
                df = df.applymap(clean_format)
            time_dic[sheet_name] = df
        return time_dic
    except Exception as e:
        raise Exception(f"時程表取得失敗: {e}")

def normalize_for_match(text):
    if text is None or str(text).lower() == 'nan': return ""
    normalized = unicodedata.normalize('NFKC', str(text))
    return re.sub(r'[\s\n]+', '', normalized).strip().upper()

def extract_workplace_from_header(header_text):
    if not header_text: return "不明な拠点"
    text_str = str(header_text)
    lines = text_str.split('\n')
    num_newlines = text_str.count('\n')
    target_index = num_newlines // 2
    try:
        work_place = lines[target_index].strip() if target_index < len(lines) else lines[-1].strip()
        if not work_place:
            non_empty = [e.strip() for e in lines if e.strip()]
            if len(non_empty) >= 2: work_place = non_empty[1]
            elif non_empty: work_place = non_empty[0]
        return work_place
    except: return "解析エラー"

def pdf_reader(file_stream, target_staff):
    table_dictionary = {}
    clean_target = normalize_for_match(target_staff)
    with pdfplumber.open(file_stream) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                df = pd.DataFrame(table)
                if df.empty: continue
                header_val = df.iloc[0, 0]
                current_workplace = extract_workplace_from_header(header_val)
                search_col = df.iloc[:, 0].apply(normalize_for_match)
                found_indices = [i for i, val in enumerate(search_col) if clean_target in val]
                if not found_indices: continue
                for idx in found_indices:
                    my_data = df.iloc[[idx]].copy()
                    others_data = df[df.index != idx].copy()
                    key_name = current_workplace
                    cnt = 2
                    while key_name in table_dictionary:
                        key_name = f"{current_workplace}_{cnt}"; cnt += 1
                    table_dictionary[key_name] = [my_data.reset_index(drop=True), others_data.reset_index(drop=True)]
    return table_dictionary

def data_integration(pdf_dic, time_schedule_dic):
    integrated_dic = {}
    for place_name, pdf_data in pdf_dic.items():
        norm_place = normalize_for_match(place_name)
        matched_key = None
        for k in time_schedule_dic.keys():
            if normalize_for_match(k) in norm_place or norm_place in normalize_for_match(k):
                matched_key = k; break
        if matched_key:
            integrated_dic[place_name] = [pdf_data[0], pdf_data[1], time_schedule_dic[matched_key]]
    return integrated_dic

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", key])
    my_time_shift = time_schedule[time_schedule.iloc[:, 1] == shift_info]
    if not my_time_shift.empty:
        prev_val = ""
        for t_col in range(3, time_schedule.shape[1]):
            current_val = my_time_shift.iloc[0, t_col]
            if current_val != prev_val:
                if current_val != "": 
                    mask_handing_over = (time_schedule.iloc[:, t_col] == prev_val) & (time_schedule.iloc[:, 1] != shift_info)
                    mask_taking_over = (time_schedule.iloc[:, t_col] == current_val) & (time_schedule.iloc[:, 1] != shift_info)
                    handing_over = ""; taking_over = ""
                    for i in range(2):
                        mask = mask_handing_over if i == 0 else mask_taking_over
                        search_codes = time_schedule.loc[mask, time_schedule.columns[1]]
                        target_rows = other_staff_shift[other_staff_shift.iloc[:, col].isin(search_codes)]
                        names = '・'.join(target_rows.iloc[:, 0].unique().astype(str))
                        if i == 0: handing_over = f"to {names}" if names else ""
                        else: taking_over = f"【{current_val}】from {names}" if names else f"【{current_val}】"
                    start_time = time_schedule.iloc[0, t_col]
                    final_rows.append([f"{handing_over}=>{taking_over}", target_date, start_time, target_date, "", "False", "", key])
                else:
                    if len(final_rows) > 0 and final_rows[-1][5] == "False":
                        final_rows[-1][4] = time_schedule.iloc[0, t_col]
            prev_val = current_val

def process_full_month(integrated_dic, year, month):
    """1日から月末まで全ての日付をループして処理する"""
    all_final_rows = []
    num_days = calendar.monthrange(year, month)[1]
    
    for day in range(1, num_days + 1):
        target_date_str = f"{year}-{month:02d}-{day:02d}"
        # PDFの列は 1日 = index 1
        current_col = day 
        
        for place_key, data_list in integrated_dic.items():
            my_shift, other_shift, time_sched = data_list
            if current_col >= my_shift.shape[1]: continue
            
            raw_val = str(my_shift.iloc[0, current_col])
            items = [i.strip() for i in re.split(r'[,、\s\n]+', raw_val) if i.strip()]
            master_codes = [normalize_for_match(x) for x in time_sched.iloc[:, 1].tolist()]
            
            for item in items:
                if normalize_for_match(item) in master_codes:
                    shift_cal(place_key, target_date_str, current_col, item, my_shift, other_shift, time_sched, all_final_rows)
                else:
                    all_final_rows.append([item, target_date_str, "", target_date_str, "", "True", "", place_key])
    return all_final_rows
