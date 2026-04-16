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
    """
    ファイル名から年月を抽出。
    ご提案のアルゴリズム：空白を除去し、数字の桁数で西暦/和暦を判定。
    """
    if not text: return None, None
    
    # 1. 全角を半角に変換し、すべての空白（全角・半角）を除去
    text = unicodedata.normalize('NFKC', text)
    clean_text = re.sub(r'\s+', '', text)
    
    # 2. 月を特定 (「数字+月」または「(数字)」または「.数字」など)
    # まず「〇月」という表現を探す
    month_match = re.search(r'(\d{1,2})月', clean_text)
    if not month_match:
        # 「〇月」がない場合、括弧内の数字や区切り記号の後の数字を探す
        month_match = re.search(r'[\(\（\.\-/](\d{1,2})[\)\）\.\-/]?\.pdf', clean_text, re.IGNORECASE)
    
    # 3. 年を特定
    # 数字の塊をすべて抽出
    nums = re.findall(r'\d+', clean_text)
    
    y_val, m_val = None, None
    
    # 月の値を確定
    if month_match:
        m_val = int(month_match.group(1))
    
    # 年の値を確定
    for n in nums:
        val = int(n)
        # 4桁なら西暦
        if len(n) == 4:
            y_val = val
        # 2桁で、かつ月として既に使われていない、あるいは13以上なら年(26年など)とみなす
        elif len(n) == 2 and y_val is None:
            if m_val is None or val != m_val or clean_text.find(n) < clean_text.find(str(m_val) + '月'):
                y_val = 2000 + val
                
    # バリデーション
    if y_val and m_val and 1 <= m_val <= 12:
        return y_val, m_val
        
    # フォールバック: 従来の正規表現も併用
    match_fallback = re.search(r'(\d{2,4}).*?(\d{1,2})', clean_text)
    if match_fallback:
        y, m = int(match_fallback.group(1)), int(match_fallback.group(2))
        if y < 100: y += 2000
        if 1 <= m <= 12: return y, m
            
    return None, None

def extract_max_day_from_pdf(pdf_stream):
    """PDF内の日付ヘッダーから最大日（28-31）を特定"""
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
    """1日のセル付近から曜日を抽出"""
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
    """Google Driveから時程表を取得"""
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
        full_df = pd.read_excel(fh, header=None, engine='openpyxl', sheet_name=0)
        location_rows = full_df[full_df.iloc[:, 0].notna()].index.tolist()
        location_data_dic = {}
        for i, start_row in enumerate(location_rows):
            end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
            location_name = str(full_df.iloc[start_row, 0]).strip()
            temp_range = full_df.iloc[start_row:end_row, :].copy()
            current_col_limit = len(temp_range.columns)
            for col_idx in range(3, len(temp_range.columns)):
                val = temp_range.iloc[0, col_idx]
                if pd.isna(val) or val == "": continue
                try: float(val)
                except: current_col_limit = col_idx; break
            data_range = temp_range.iloc[:, 0:current_col_limit].copy().reset_index(drop=True)
            for col in range(1, data_range.shape[1]):
                time_val = data_range.iloc[0, col]
                if pd.notna(time_val) and isinstance(time_val, (int, float)):
                    h = int(time_val); m = int(round((time_val - h) * 60))
                    data_range.iloc[0, col] = f"{h}:{m:02d}"
            location_data_dic[location_name] = data_range.fillna('')
        return location_data_dic
    except Exception as e: raise e

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
    final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", key])
    my_time_shift = time_schedule[time_schedule.iloc[:, 1].astype(str).str.strip() == str(shift_info).strip()]
    if my_time_shift.empty: return
    prev_val = ""
    for t_col in range(2, time_schedule.shape[1]):
        current_val = str(my_time_shift.iloc[0, t_col])
        if current_val.lower() == 'nan': current_val = ""
        if current_val != prev_val:
            if current_val != "":
                mask = (time_schedule.iloc[:, t_col].astype(str) == current_val) & (time_schedule.iloc[:, 1] != shift_info)
                codes = time_schedule.loc[mask, time_schedule.columns[1]].tolist()
                names = []
                for code in codes:
                    matches = other_staff_shift[other_staff_shift.iloc[:, col].astype(str).str.contains(str(code))]
                    names.extend([n.split('\n')[0].strip() for n in matches.iloc[:, 0].tolist() if n])
                u_names = "・".join(list(set(names)))
                subj = f"【{current_val}】from {u_names}" if u_names else f"【{current_val}】"
                final_rows.append([subj, target_date, str(time_schedule.iloc[0, t_col]), target_date, "", "False", "", key])
            else:
                if final_rows and final_rows[-1][5] == "False":
                    final_rows[-1][4] = str(time_schedule.iloc[0, t_col])
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
