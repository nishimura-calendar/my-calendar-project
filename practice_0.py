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
    if m_val is None:
        for n in nums:
            val = int(n)
            if 1 <= val <= 12 and (y_val is None or val != (y_val % 100)):
                m_val = val
                break
    if y_val and m_val and 1 <= m_val <= 12:
        return y_val, m_val
    return None, None

def extract_max_day_from_pdf(pdf_stream):
    try:
        pdf_stream.seek(0)
        with open("temp_days.pdf", "wb") as f: f.write(pdf_stream.getbuffer())
        tables = camelot.read_pdf("temp_days.pdf", pages='1', flavor='lattice')
        if tables:
            df = tables[0].df
            header_text = " ".join(df.iloc[0:4, :].values.flatten().astype(str))
            days = re.findall(r'\b(2[89]|3[01])\b', header_text)
            if days: 
                return int(max(map(int, days)))
    except: pass
    return None

def extract_first_weekday_from_pdf(pdf_stream):
    try:
        pdf_stream.seek(0)
        with open("temp_wd.pdf", "wb") as f: f.write(pdf_stream.getbuffer())
        tables = camelot.read_pdf("temp_wd.pdf", pages='1', flavor='lattice')
        if tables:
            df = tables[0].df
            for col in range(1, min(12, df.shape[1])):
                cell_text = "".join(df.iloc[0:5, col].astype(str))
                match = re.search(r'[（\(]([月火水木金土日])[）\)]', cell_text)
                if match: return match.group(1)
    except: pass
    return None

def time_schedule_from_drive(service, file_id):
    """
    時程表スプレッドシートの解析。
    D列(インデックス3)からスキャンし、数値または時刻以外の文字列が出現するまでを有効な時間範囲とする。
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
        
        # 混在エラー回避のため一旦すべて文字列として読み込む
        full_df = pd.read_excel(fh, header=None, engine='openpyxl', sheet_name=0, dtype=str)
        
        location_rows = full_df[full_df.iloc[:, 0].notna()].index.tolist()
        location_data_dic = {}
        
        for i, start_row in enumerate(location_rows):
            end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
            location_name = str(full_df.iloc[start_row, 0]).strip()
            temp_range = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
            
            # 3列目(D列)から時間データの終端を探す
            first_time_col = 3
            last_time_col = first_time_col
            
            for col in range(first_time_col, temp_range.shape[1]):
                val = temp_range.iloc[0, col]
                if pd.isna(val) or str(val).lower() == "nan" or str(val).strip() == "":
                    # 空白はスキップして継続（暫定）
                    continue
                
                # 数値(6.25等)または時刻形式(6:15等)かチェック
                valid_time = False
                try:
                    # 数値なら時刻形式文字列に変換
                    f_val = float(val)
                    if 0 <= f_val <= 28: # 最大28時まで想定
                        h = int(f_val)
                        m = int(round((f_val - h) * 60))
                        temp_range.iloc[0, col] = f"{h}:{m:02d}"
                        valid_time = True
                except ValueError:
                    # 数値でない場合、":"が含まれていれば時刻とみなす
                    if ":" in str(val):
                        temp_range.iloc[0, col] = str(val).strip()
                        valid_time = True
                
                # 時刻でない文字列（出勤、退勤など）が出現したらループ停止
                if not valid_time:
                    break
                
                last_time_col = col
            
            # 拠点データとして抽出（不要な末尾列を除去）
            extracted_df = temp_range.iloc[:, :last_time_col + 1].copy()
            location_data_dic[location_name] = extracted_df.fillna('')
            
        return location_data_dic
    except Exception as e:
        raise e

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

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """
    確定した時間範囲（3列目〜）に基づいてスケジュール解析を実施。
    """
    time_shift = time_schedule.fillna("").astype(str)
    
    # 勤務記号がB列(インデックス1)にあるか照合
    if (time_shift.iloc[:, 1] == str(shift_info)).any():
        final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", key])
        my_time_shift = time_shift[time_shift.iloc[:, 1] == str(shift_info)]
        
        if not my_time_shift.empty:
            prev_val = ""
            # 3列目以降、保持されているデータの終端までループ
            for t_col in range(3, my_time_shift.shape[1]):
                current_val = my_time_shift.iloc[0, t_col]
                
                if current_val != prev_val:
                    time_val = time_shift.iloc[0, t_col]
                    
                    if current_val != "":
                        # 新しい業務の開始
                        final_rows.append([f"【{current_val}】", target_date, time_val, target_date, "", "False", "", key])
                    else:
                        # 業務の終了・退勤判定
                        suffix = ""
                        # 以降のセルがすべて空白なら退勤
                        if (my_time_shift.iloc[0, t_col:] == "").all():
                            suffix = " => (退勤)"
                        
                        if len(final_rows) > 0:
                            if not final_rows[-1][0].endswith("(退勤)"):
                                final_rows[-1][0] += suffix
                            final_rows[-1][4] = time_val
                
                prev_val = current_val

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
