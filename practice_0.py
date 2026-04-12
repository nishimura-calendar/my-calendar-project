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
    """Google Drive APIへのサービスオブジェクトを作成"""
    creds = service_account.Credentials.from_service_account_info(
        secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build('drive', 'v3', credentials=creds)

def time_schedule_from_drive(service, file_id):
    """Google Driveから時程表を読み込み、時刻軸をクレンジングする"""
    try:
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done: _, done = downloader.next_chunk()
        fh.seek(0)
        
        full_df = pd.read_excel(fh, header=None, engine='openpyxl')
        
        # 1. 有効な列範囲の判定 (数値/時刻のみを対象にする)
        col_limit = len(full_df.columns)
        for i in range(2, len(full_df.columns)):
            val = full_df.iloc[0, i]
            try:
                float(val)
            except (ValueError, TypeError):
                col_limit = i
                break

        # 2. 勤務地(ブロック)の特定
        location_rows = full_df[full_df.iloc[:, 0].notna()].index.tolist()
        processed_sheets = {}

        for i, start_row in enumerate(location_rows):
            end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
            location_name = str(full_df.iloc[start_row, 0]).strip()
            
            # 範囲抽出と時刻クレンジング
            df_part = full_df.iloc[start_row:end_row, 0:col_limit].copy().reset_index(drop=True)
            
            for col in range(2, df_part.shape[1]):
                val = df_part.iloc[0, col]
                try:
                    num_val = float(val)
                    if 0 < num_val < 1:
                        ts = int(num_val * 24 * 3600)
                        df_part.iloc[0, col] = f"{ts // 3600:02d}:{(ts % 3600) // 60:02d}"
                    else:
                        df_part.iloc[0, col] = f"{int(num_val):02d}:00"
                except:
                    pass
            
            processed_sheets[location_name] = df_part

        return processed_sheets
    except Exception as e:
        print(f"Error: {e}")
        return None

def normalize_for_match(text):
    if not isinstance(text, str): return ""
    return unicodedata.normalize('NFKC', re.sub(r'\s+', '', text)).strip().lower()

def pdf_reader(file_stream, target_staff):
    pdf_data = {}
    target_norm = normalize_for_match(target_staff)
    with pdfplumber.open(file_stream) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if not table: continue
            df = pd.DataFrame(table)
            for i, row in df.iterrows():
                if target_norm in normalize_for_match(str(row[0])):
                    location = str(row[1]) if len(row) > 1 else "Unknown"
                    pdf_data[location] = df.copy()
                    pdf_data[location + "_target_row_idx"] = i 
    return pdf_data

def data_integration(pdf_dic, time_dic):
    integrated = {}
    logs = []
    for loc_key, pdf_df in pdf_dic.items():
        if "_target_row_idx" in loc_key: continue
        pdf_loc = normalize_for_match(loc_key)
        matched_sheet = None
        for sn in time_dic.keys():
            sn_norm = normalize_for_match(sn)
            if sn_norm in pdf_loc or pdf_loc in sn_norm:
                matched_sheet = sn
                break
        
        if matched_sheet:
            logs.append(f"✅ マッチ: {loc_key} -> {matched_sheet}")
            idx = pdf_dic[loc_key + "_target_row_idx"]
            integrated[matched_sheet] = [pdf_df.iloc[[idx], :], pdf_df.drop(idx), time_dic[matched_sheet]]
        else:
            logs.append(f"❌ 不一致: {loc_key} (時程表に該当なし)")
    return integrated, logs

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    # 終日
    final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", key])
    
    my_time_shift = time_schedule[time_schedule.iloc[:, 1].astype(str) == shift_info]
    if my_time_shift.empty: return

    prev_val = ""
    for t_col in range(2, time_schedule.shape[1]):
        current_val = str(my_time_shift.iloc[0, t_col]) if t_col < my_time_shift.shape[1] else ""
        if current_val.lower() == 'nan': current_val = ""

        if current_val != prev_val:
            if current_val != "":
                # 交代相手
                mask_curr = (time_schedule.iloc[:, t_col].astype(str) == current_val) & (time_schedule.iloc[:, 1] != shift_info)
                codes = time_schedule.loc[mask_curr, time_schedule.columns[1]].tolist()
                names = "・".join([str(n).split('\n')[0] for n in other_staff_shift[other_staff_shift.iloc[:, col].isin(codes)].iloc[:, 0].unique() if n])
                
                subj = f"【{current_val}】from {names}" if names else f"【{current_val}】"
                final_rows.append([subj, target_date, time_schedule.iloc[0, t_col], target_date, "", "False", "", key])
            else:
                if final_rows and final_rows[-1][5] == "False":
                    final_rows[-1][4] = time_schedule.iloc[0, t_col]
        prev_val = current_val

def process_full_month(integrated_dic, year, month):
    all_final_rows = []
    num_days = calendar.monthrange(year, month)[1]
    for day in range(1, num_days + 1):
        # 以前うまくいっていた current_col = day (Index 1) に設定
        # もしズレる場合はここを day + 1 に調整してください
        current_col = day + 1 
        for place_key, data in integrated_dic.items():
            my_shift, other_shift, time_sched = data
            if current_col >= my_shift.shape[1]: continue
            val = str(my_shift.iloc[0, current_col])
            if not val or val.lower() == 'nan' or val.strip() == "": continue
            
            items = [i.strip() for i in re.split(r'[,、\s\n]+', val) if i.strip()]
            for item in items:
                shift_cal(place_key, f"{year}-{month:02d}-{day:02d}", current_col, item, my_shift, other_shift, time_sched, all_final_rows)
    return all_final_rows
