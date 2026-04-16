import pandas as pd
import pdfplumber
import camelot
import unicodedata
import re
import io
import calendar
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account

def get_gdrive_service(secrets):
    """Google Drive APIへのサービスオブジェクトを作成"""
    creds = service_account.Credentials.from_service_account_info(
        secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build('drive', 'v3', credentials=creds)

def normalize_text(text):
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def extract_year_month_from_text(text):
    """テキスト（ファイル名など）から年月を抽出"""
    if not text: return None, None
    match = re.search(r'(\d{2,4})\s*[年/]\s*(\d{1,2})\s*月?', text)
    if match:
        y = int(match.group(1))
        if y < 100: y += 2000 # 26 -> 2026
        return y, int(match.group(2))
    return None, None

def extract_year_month_from_pdf(pdf_stream):
    """PDFの第1ページテキストから年月を抽出"""
    try:
        pdf_stream.seek(0)
        with pdfplumber.open(pdf_stream) as pdf:
            text = pdf.pages[0].extract_text()
            return extract_year_month_from_text(text)
    except: return None, None

def extract_max_day_from_pdf(pdf_stream):
    """PDFテーブルから最大の日付（月末日）を推測"""
    try:
        pdf_stream.seek(0)
        with open("temp_days.pdf", "wb") as f:
            f.write(pdf_stream.getbuffer())
        tables = camelot.read_pdf("temp_days.pdf", pages='1', flavor='lattice')
        if tables:
            df = tables[0].df
            all_text = " ".join(df.iloc[0:2, :].values.flatten().astype(str))
            days = re.findall(r'\b(2[89]|3[01])\b', all_text)
            if days:
                return int(max(days))
    except: pass
    return None

def extract_first_weekday_from_pdf(pdf_stream):
    """PDFテーブルの1日の列から曜日を抽出"""
    try:
        pdf_stream.seek(0)
        with open("temp_wd.pdf", "wb") as f:
            f.write(pdf_stream.getbuffer())
        tables = camelot.read_pdf("temp_wd.pdf", pages='1', flavor='lattice')
        if tables:
            df = tables[0].df
            for col in range(1, min(6, df.shape[1])):
                cell_text = "".join(df.iloc[0:3, col].astype(str))
                match = re.search(r'[（\(]([月火水木金土日])[）\)]', cell_text)
                if match: return match.group(1)
    except: pass
    return None

# --- ① 指定された基幹関数 ---
def time_schedule_from_drive(service, file_id):
    """勤務地ごとに列境界と時間を独立判定して抽出"""
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
        while not done:
            _, done = downloader.next_chunk()
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
                try:
                    float(val)
                except (ValueError, TypeError):
                    current_col_limit = col_idx
                    break
            
            data_range = temp_range.iloc[:, 0:current_col_limit].copy().reset_index(drop=True)
            data_range = data_range.astype(object)

            for col in range(1, data_range.shape[1]):
                time_val = data_range.iloc[0, col]
                if pd.notna(time_val) and isinstance(time_val, (int, float)):
                    hours = int(time_val)
                    minutes = int(round((time_val - hours) * 60))
                    data_range.iloc[0, col] = f"{hours}:{minutes:02d}"
            
            location_data_dic[location_name] = data_range.fillna('')
        return location_data_dic
    except Exception as e:
        raise e

# --- ② 指定された基幹関数 ---
def pdf_reader(pdf_stream, target_staff):
    """PDFからスタッフ行を抽出"""
    clean_target = normalize_text(target_staff)
    pdf_stream.seek(0)
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    try:
        tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    except Exception:
        return {}

    table_dictionary = {}
    for table in tables:
        df = table.df
        if not df.empty:
            text = str(df.iloc[0, 0])
            lines = text.splitlines()
            target_idx = text.count('\n') // 2
            work_place = lines[target_idx] if target_idx < len(lines) else (lines[-1] if lines else "Unknown")
            df = df.fillna('')
            search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
            matched_indices = df.index[search_col == clean_target].tolist()
            if matched_indices:
                idx = matched_indices[0]
                my_daily = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
                others = df.drop([0, idx, idx+1] if idx+1 < len(df) else [0, idx]).copy().reset_index(drop=True)
                table_dictionary[work_place] = [my_daily, others]
    return table_dictionary

# --- ③ 指定された基幹関数 ---
def data_integration(pdf_dic, time_dic):
    """PDFと時程表の勤務地名を紐付ける。"""
    integrated = {}
    for pk, pv in pdf_dic.items():
        match = next((k for k in time_dic.keys() if normalize_text(pk) in normalize_text(k)), None)
        if match: integrated[match] = pv + [time_dic[match]]
    return integrated, []

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """個別のシフト詳細計算"""
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
                    if not str(code).strip(): continue
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
    """月間ループ"""
    all_final_rows = []
    num_days = calendar.monthrange(year, month)[1]
    for day in range(1, num_days + 1):
        target_date_str = f"{year}-{month:02d}-{day:02d}"
        current_col = day + 1 
        for place_key, (my_row, others, time_sched) in integrated_dic.items():
            if current_col >= my_row.shape[1]: continue
            val = str(my_row.iloc[0, current_col])
            if not val or val.strip() == "" or val.lower() == 'nan': continue
            items = [i.strip() for i in re.split(r'[,、\s\n]+', val) if i.strip()]
            for item in items:
                shift_cal(place_key, target_date_str, current_col, item, my_row, others, time_sched, all_final_rows)
    return all_final_rows
