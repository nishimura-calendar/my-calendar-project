import pandas as pd
import camelot
import re
import calendar
import io
import csv
from googleapiclient.http import MediaIoBaseUpload

def get_calc_date_info(y, m):
    """① ファイル名から算出する日数と第一曜日"""
    _, last_day = calendar.monthrange(y, m)
    w_list = ["月", "火", "水", "木", "金", "土", "日"]
    first_w = w_list[calendar.weekday(y, m, 1)]
    return last_day, first_w

def load_master_from_sheets(service, spreadsheet_id):
    """時程表を読み込み、勤務地をキーに辞書登録"""
    spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    time_dic = {}
    for s in spreadsheet.get('sheets', []):
        title = s.get("properties", {}).get("title")
        res = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=f"'{title}'!A1:Z300").execute()
        vals = res.get('values', [])
        if not vals: continue
        df = pd.DataFrame(vals).fillna('')

        current_loc, start_idx = None, 0
        for i in range(len(df)):
            val_a = str(df.iloc[i, 0]).strip()
            if val_a != "":
                if current_loc:
                    time_dic[current_loc] = process_time_block(df.iloc[start_idx:i, :])
                current_loc, start_idx = val_a, i
        if current_loc:
            time_dic[current_loc] = process_time_block(df.iloc[start_idx:, :])
    return time_dic

def process_time_block(block):
    """時程表の時間変換処理"""
    def to_time(v):
        try:
            f = float(v)
            return f"{int(f):02d}:{int(round((f-int(f))*60)):02d}"
        except: return v
    time_cols = []
    for col in range(3, block.shape[1]):
        try:
            float(block.iloc[0, col])
            time_cols.append(col)
        except:
            if time_cols: break
    res_df = block.iloc[:, [0, 1, 2] + time_cols].copy()
    for i in range(len(time_cols)):
        res_df.iloc[0, 3 + i] = to_time(res_df.iloc[0, 3 + i])
    return res_df

def analyze_pdf_structure(pdf_path, y, m):
    """第一関門・データ抽出 [cite: 2]"""
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    if not tables: return None, "PDF表抽出失敗"
    df = tables[0].df
    raw_0_0 = str(df.iloc[0, 0]).strip()
    
    calc_last_day, calc_first_w = get_calc_date_info(y, m)
    nums = [int(n) for n in re.findall(r'\d+', raw_0_0)]
    pdf_last_day = max(nums) if nums else 0
    pdf_first_w = (re.findall(r'[月火水木金土日]', raw_0_0) + [""])[0]
    
    if not (pdf_last_day == calc_last_day and pdf_first_w == calc_first_w):
        return None, f"不一致：計算={calc_last_day}({calc_first_w}) / PDF={pdf_last_day}({pdf_first_w})"

    location = re.sub(r'\(?[月火水木金土日]\)?', '', raw_0_0)
    location = re.sub(r'\d+[\s～~-]+\d+', '', location)
    location = re.sub(r'\b([1-9]|[12][0-9]|3[01])\b', '', location)
    location = re.sub(r'[年月日で\s/：:-]', '', location).strip()
    
    rows = []
    rows.append([""] + df.iloc[0, 1:].tolist()) 
    rows.append([location] + df.iloc[1, 1:].tolist())
    
    staff_names = []
    for i in range(2, len(df)):
        cell = str(df.iloc[i, 0]).strip()
        val = cell.split('\n')[0] if i % 2 == 0 else cell
        rows.append([val] + df.iloc[i, 1:].tolist())
        
        if i % 2 == 0 and val and val != location:
            staff_names.append(val)
            
    return {"df": pd.DataFrame(rows), "location": location, "staff_list": staff_names}, "通過"

def extract_target_data(df, target_staff, location):
    """第3関門：my_daily_shift, other_daily_shiftの抽出 [cite: 2]"""
    if target_staff not in df[0].values:
        return None
        
    idx = df[df[0] == target_staff].index[0]
    my_daily_shift = df.iloc[idx : idx+2, :].copy()
    
    other_indices = []
    for i in range(2, len(df)):
        val_0 = str(df.iloc[i, 0]).strip()
        if i != idx and i != (idx + 1) and val_0 != location and val_0 != "":
            other_indices.append(i)
            
    other_daily_shift = df.iloc[other_indices, :].copy()
    
    return {
        "my_daily_shift": my_daily_shift,
        "other_daily_shift": other_daily_shift
    }

def create_and_upload_calendar_csv(drive_service, folder_id, y, m, location, my_shift, time_schedule):
    """[3] カレンダー登録 CSV作成とDrive保存処理 """
    events_holiday = []
    events_key = []
    events_other = []

    holiday_keywords = ["休", "休日", "公休", "有休", "有給"]
    header = ["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location", "Private"]

    has_sub_row = len(my_shift) > 1

    for col in range(1, my_shift.shape[1]):
        info = str(my_shift.iloc[0, col]).strip()
        if not info:
            continue

        target_date = f"{y:04d}/{m:02d}/{col:02d}"
        
        if info in holiday_keywords:
            events_holiday.append([info, target_date, "", target_date, "", "True", "", "", "False"])
        elif info == "本町":
            # 本町専用ロジック (例: "9 ① 14" -> Start 09:00, End 14:00) 
            sub_info = str(my_shift.iloc[1, col]).strip() if has_sub_row else ""
            start_time, end_time = "", ""
            m_match = re.search(r'(\d+)\s*[①②③④⑤]\s*(\d+)', sub_info)
            if m_match:
                start_time = f"{int(m_match.group(1)):02d}:00"
                end_time = f"{int(m_match.group(2)):02d}:00"
            events_key.append(["本町", target_date, start_time, target_date, end_time, "False", "", "本町", "False"])
        elif info in time_schedule.iloc[:, 1].values:
            # time_schedule連動ロジック 
            t_row = time_schedule[time_schedule.iloc[:, 1] == info].iloc[0]
            start_time, end_time = "", ""
            started = False
            
            for t_col in range(3, len(t_row)):
                val = str(t_row.iloc[t_col]).strip()
                if val != "" and not started:
                    start_time = str(time_schedule.iloc[0, t_col])
                    started = True
                elif val == "" and started:
                    end_time = str(time_schedule.iloc[0, t_col])
                    break
            
            if started and end_time == "":
                end_time = str(time_schedule.iloc[0, -1])
                
            events_key.append([info, target_date, start_time, target_date, end_time, "False", "", location, "False"])
        else:
            # その他イベント 
            events_other.append([info, target_date, "", target_date, "", "True", "", "", "False"])

    uploaded_files = {}
    
    def save_to_drive(data_list, suffix):
        if not data_list: return
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(header)
        writer.writerows(data_list)
        
        filename = f"{y:04d}年{m:02d}月_{suffix}.csv"
        file_metadata = {'name': filename, 'parents': [folder_id]}
        media = MediaIoBaseUpload(io.BytesIO(output.getvalue().encode('utf-8-sig')), mimetype='text/csv')
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        uploaded_files[filename] = file.get('id')

    save_to_drive(events_holiday, "休")
    save_to_drive(events_key, location)
    save_to_drive(events_other, "イベント")
    
    return uploaded_files
