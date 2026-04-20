import pandas as pd
import camelot
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

def normalize_text(text):
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def extract_year_month_from_text(text):
    """ファイル名等から年月を抽出する（エラー回避のため完全実装）"""
    if not text: return None, None
    text = unicodedata.normalize('NFKC', text)
    clean_text = re.sub(r'\s+', '', text)
    y_val, m_val = None, None
    
    # 月の抽出 (例: 12月)
    month_match = re.search(r'(\d{1,2})月', clean_text)
    if month_match:
        m_val = int(month_match.group(1))
    
    # 年の抽出 (4桁または2桁)
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

def time_schedule_from_drive(service, file_id):
    """時程表スプレッドシートを解析"""
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
        
        full_df = pd.read_excel(fh, header=None, engine='openpyxl', sheet_name=0, dtype=str)
        location_rows = full_df[full_df.iloc[:, 0].notna()].index.tolist()
        location_data_dic = {}
        
        for i, start_row in enumerate(location_rows):
            end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
            location_name = str(full_df.iloc[start_row, 0]).strip()
            temp_range = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
            
            time_row = temp_range.iloc[0, :]
            first_num_col, last_num_col = None, None
            for idx, val in enumerate(time_row):
                if idx < 1: continue 
                try:
                    float(val)
                    if first_num_col is None: first_num_col = idx
                    last_num_col = idx
                except: continue
            
            if first_num_col is not None:
                start_c = max(1, first_num_col - 1)
                end_c = last_num_col + 1
                selected_cols = [0, 1] + list(range(start_c, end_c))
                temp_range = temp_range.iloc[:, selected_cols].copy()
                
                for c in range(2, len(temp_range.columns)):
                    v = temp_range.iloc[0, c]
                    try:
                        fv = float(v)
                        h = int(fv); m = int(round((fv - h) * 60))
                        temp_range.iloc[0, c] = f"{h}:{m:02d}"
                    except: pass
            
            location_data_dic[location_name] = temp_range.fillna('')
        return location_data_dic
    except Exception as e:
        raise e

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """
    引継ぎロジックの実装
    受取(From): 自分の開始時、t_col-1 に同じ場所を担当していた人を探す
    渡却(To): 自分の終了時、t_col にその場所を引き継ぐ人を探す
    """
    time_shift = time_schedule.fillna("").astype(str)
    
    # 終日イベント(シフトコード)
    if (time_shift.iloc[:, 1] == shift_info).any():
        final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", key])
        
        my_time_shift = time_shift[time_shift.iloc[:, 1] == shift_info]
        if not my_time_shift.empty:
            prev_val = ""
            # 時間列をスキャン
            for t_col in range(2, my_time_shift.shape[1]):
                current_val = my_time_shift.iloc[0, t_col]
                time_header = time_shift.iloc[0, t_col]

                if current_val != prev_val:
                    # --- 渡却 (Handing over / To) ---
                    # 前に業務(prev_val)があり、現在(t_col)で変化した場合
                    if final_rows and final_rows[-1][5] == "False":
                        # 終了時間を確定
                        final_rows[-1][4] = time_header
                        
                        handing_over_staff = ""
                        if prev_val != "":
                            # t_col（現在）で、さっきまで自分がやっていた業務(prev_val)を引き継ぐ人を探す
                            mask_to = (time_shift.iloc[:, t_col] == prev_val) & (time_shift.iloc[:, 1] != shift_info)
                            to_codes = time_shift.loc[mask_to, time_shift.columns[1]].tolist()
                            
                            for c in to_codes:
                                if c == "": continue
                                match = other_staff_shift[other_staff_shift.iloc[:, col].astype(str).str.contains(re.escape(str(c)), na=False)]
                                if not match.empty:
                                    handing_over_staff = str(match.iloc[0, 0]).split('\n')[0].strip()
                                    break
                        
                        if handing_over_staff:
                            final_rows[-1][0] += f" => {handing_over_staff}"
                        
                        # 退勤判定: この後一切業務がない場合
                        if current_val == "" and (my_time_shift.iloc[0, t_col:] == "").all():
                            if "=>" not in final_rows[-1][0]:
                                final_rows[-1][0] += " => (退勤)"
                            else:
                                final_rows[-1][0] += " (退勤)"

                    # --- 受取 (Taking over / From) ---
                    # 新しい業務(current_val)が始まった場合
                    if current_val != "":
                        taking_over_department = f"【{current_val}】"
                        taking_over_staff = ""
                        
                        # t_col-1 (一つ前の時間) で、今から自分がやる業務(current_val)をしていた人を探す
                        if t_col > 2:
                            mask_from = (time_shift.iloc[:, t_col-1] == current_val) & (time_shift.iloc[:, 1] != shift_info)
                            from_codes = time_shift.loc[mask_from, time_shift.columns[1]].tolist()
                            
                            for c in from_codes:
                                if c == "": continue
                                match = other_staff_shift[other_staff_shift.iloc[:, col].astype(str).str.contains(re.escape(str(c)), na=False)]
                                if not match.empty:
                                    taking_over_staff = f"{str(match.iloc[0, 0]).split('\n')[0].strip()} => "
                                    break
                        
                        subject = f"{taking_over_staff}{taking_over_department}"
                        
                        # 新規予定追加 (終了時間は次のループの「渡却」でセットされる)
                        final_rows.append([
                            subject, target_date, time_header, target_date, "", "False", "", key
                        ])
                        
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
            header = str(df.iloc[0, 0]).splitlines()
            work_place = header[len(header)//2] if header else "Unknown"
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
        for place_key, (my_row, others, time_sched) in integrated_dic.items():
            if day + 1 >= my_row.shape[1]: continue
            val = str(my_row.iloc[0, day + 1])
            if not val or val.strip() == "" or val.lower() == 'nan': continue
            for item in [i.strip() for i in re.split(r'[,、\s\n]+', val) if i.strip()]:
                shift_cal(place_key, target_date_str, day + 1, item, my_row, others, time_sched, all_final_rows)
    return all_final_rows
