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
    """
    Google Driveから時程表を読み込み、時刻軸のクレンジングと
    データの有効範囲(col_limit)を自動判定する (考察2.pyのロジックを統合)
    """
    try:
        file_metadata = service.files().get(fileId=file_id, fields='mimeType').execute()
        mime_type = file_metadata.get('mimeType')

        if mime_type == 'application/vnd.google-apps.spreadsheet':
            request = service.files().export_media(
                fileId=file_id,
                mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        else:
            request = service.files().get_media(fileId=file_id)
        
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        
        fh.seek(0)
        # 考察2.pyに合わせて engine='openpyxl' を指定
        all_sheets_raw = pd.read_excel(fh, sheet_name=None, header=None, engine='openpyxl')
        
        processed_sheets = {}

        for sheet_name, full_df in all_sheets_raw.items():
            # 1. 列の境界（文字列が現れる列）を自動判定
            col_limit = len(full_df.columns)
            for i in range(2, len(full_df.columns)):
                val = full_df.iloc[0, i]
                try:
                    # 数値として解釈できるか試行
                    float(val)
                except (ValueError, TypeError):
                    # 数値に変換できない(例: 「出勤」) = 境界と判断
                    col_limit = i
                    break
            
            # 2. 勤務地(ブロック)ごとの分割は、後のdata_integrationで行うため
            # ここでは全体のクレンジングのみ実施
            df_cleaned = full_df.iloc[:, 0:col_limit].copy()
            
            # 3. 時間表記の変換 (0.25 -> "06:00:00")
            for col in range(2, df_cleaned.shape[1]):
                val = df_cleaned.iloc[0, col]
                try:
                    num_val = float(val)
                    if 0 < num_val < 1: # 1未満の数値は時刻シリアル値とみなす
                        total_seconds = int(num_val * 24 * 3600)
                        hours = total_seconds // 3600
                        minutes = (total_seconds % 3600) // 60
                        seconds = total_seconds % 60
                        df_cleaned.iloc[0, col] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                    else:
                        df_cleaned.iloc[0, col] = str(int(num_val)) if num_val.is_integer() else str(num_val)
                except (ValueError, TypeError):
                    pass
            
            processed_sheets[sheet_name] = df_cleaned

        return processed_sheets

    except Exception as e:
        print(f"Error fetching sheet: {e}")
        return None

def normalize_for_match(text):
    """比較用の文字列正規化"""
    if not isinstance(text, str): return ""
    text_clean = re.sub(r'\s+', '', text)
    normalized = unicodedata.normalize('NFKC', text_clean)
    return normalized.strip().upper()

def pdf_reader(file_stream, target_staff):
    """PDFから指定したスタッフのシフトを抽出"""
    pdf_data = {}
    target_staff_norm = normalize_for_match(target_staff)
    with pdfplumber.open(file_stream) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if not table: continue
            df = pd.DataFrame(table)
            for i, row in df.iterrows():
                staff_name = str(row[0])
                if target_staff_norm in normalize_for_match(staff_name):
                    location = str(row[1]) if len(row) > 1 else "Unknown"
                    pdf_data[location] = df.copy()
                    pdf_data[location + "_target_row_idx"] = i 
    return pdf_data

def data_integration(pdf_dic, time_dic):
    """PDFの勤務地と時程表のシートを紐付け"""
    integrated = {}
    for loc_key, pdf_df in pdf_dic.items():
        if "_target_row_idx" in loc_key: continue
        matched_sheet = None
        for sheet_name in time_dic.keys():
            if normalize_for_match(sheet_name) in normalize_for_match(loc_key):
                matched_sheet = sheet_name
                break
        if matched_sheet:
            target_idx = pdf_dic[loc_key + "_target_row_idx"]
            my_shift = pdf_df.iloc[[target_idx], :]
            other_shift = pdf_df.drop(target_idx)
            integrated[matched_sheet] = [my_shift, other_shift, time_dic[matched_sheet]]
    return integrated

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """
    修正版: 既にクレンジング済みのtime_scheduleを使用する前提
    """
    # 1. 終日予定
    final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", key])

    # 2. 詳細解析
    my_time_shift = time_schedule[time_schedule.iloc[:, 1].astype(str) == shift_info]
    if my_time_shift.empty:
        return

    prev_val = ""
    # クレンジング済みなので time_schedule.shape[1] まで回しても安全
    for t_col in range(2, time_schedule.shape[1]):
        current_val = str(my_time_shift.iloc[0, t_col]) if t_col < my_time_shift.shape[1] else ""
        if current_val.lower() == 'nan': current_val = ""

        if current_val != prev_val:
            if current_val != "":
                # 予定開始
                mask_prev = (time_schedule.iloc[:, t_col].astype(str) == prev_val) & (time_schedule.iloc[:, 1] != shift_info)
                mask_curr = (time_schedule.iloc[:, t_col].astype(str) == current_val) & (time_schedule.iloc[:, 1] != shift_info)

                def find_staff(mask):
                    codes = time_schedule.loc[mask, time_schedule.columns[1]].tolist()
                    rows = other_staff_shift[other_staff_shift.iloc[:, col].isin(codes)]
                    return "・".join([str(n).split('\n')[0].strip() for n in rows.iloc[:, 0].unique() if n and str(n).lower() != 'nan'])

                names_to = find_staff(mask_prev)
                names_from = find_staff(mask_curr)

                handing_over = f"to {names_to}" if names_to else ""
                taking_over = f"【{current_val}】from {names_from}" if names_from else f"【{current_val}】"
                
                subject = f"{handing_over} => {taking_over}".strip(" => ")
                start_t = time_schedule.iloc[0, t_col] # すでに時刻形式に変換済み

                final_rows.append([subject, target_date, start_t, target_date, "", "False", "", key])
            else:
                # 予定終了
                if final_rows and final_rows[-1][5] == "False":
                    final_rows[-1][4] = time_schedule.iloc[0, t_col]
        
        prev_val = current_val

def process_full_month(integrated_dic, year, month):
    """月間全日程の処理"""
    all_final_rows = []
    num_days = calendar.monthrange(year, month)[1]
    for day in range(1, num_days + 1):
        target_date_str = f"{year}-{month:02d}-{day:02d}"
        current_col = day + 1 
        for place_key, data_list in integrated_dic.items():
            my_shift, other_shift, time_sched = data_list
            if current_col >= my_shift.shape[1]: continue
            
            raw_val = str(my_shift.iloc[0, current_col])
            if not raw_val or raw_val.lower() == 'nan' or raw_val.strip() == "": continue
            
            items = [i.strip() for i in re.split(r'[,、\s\n]+', raw_val) if i.strip()]
            for item in items:
                shift_cal(place_key, target_date_str, current_col, item, my_shift, other_shift, time_sched, all_final_rows)
    return all_final_rows
