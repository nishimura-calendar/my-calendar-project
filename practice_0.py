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
    """第一関門・データ抽出（※稼働実績のあるオリジナルコードをそのまま使用）"""
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
    """第3関門：my_daily_shift, other_daily_shiftの抽出（※オリジナルコードそのまま）"""
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

# =========================================================
# [3] カレンダー登録用 新規追加ロジック
# =========================================================
def create_calendar_csv_data(y, m, location, my_shift, time_schedule):
    """カレンダー登録.csvの仕様に基づくデータ生成"""
    events = []
    header = ["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location", "Private"]
    events.append(header)

    _, last_day = calendar.monthrange(y, m)

    # 1列目〜最終列まで順次読み込む
    for col in range(1, last_day + 1):
        if col >= my_shift.shape[1]:
            break
            
        info = str(my_shift.iloc[0, col]).strip()
        if not info:
            continue
            
        target_date = f"{y:04d}/{m:02d}/{col:02d}"
        
        # (1) 時程表(time_schedule)にinfo(シフトコード)が存在する場合
        if (time_schedule.iloc[:, 1] == info).any():
            t_row = time_schedule[time_schedule.iloc[:, 1] == info].iloc[0]
            start_time = ""
            end_time = ""
            started = False
            
            # test_1.py代替: 左から右へ走査し「無→有」でstart、「有→無」でendを取得
            for c in range(3, len(t_row)):
                val = str(t_row.iloc[c]).strip()
                if val != "" and not started:
                    start_time = str(time_schedule.iloc[0, c])
                    started = True
                elif val == "" and started:
                    end_time = str(time_schedule.iloc[0, c])
                    break
                    
            if started and end_time == "":
                end_time = str(time_schedule.iloc[0, -1]) # 最後まで埋まっていた場合
                
            events.append([info, target_date, start_time, target_date, end_time, "False", "", location, "False"])
            
        # (3) info == "本町" の場合
        elif info == "本町":
            sub_info = str(my_shift.iloc[1, col]).strip() if len(my_shift) > 1 else ""
            start_time = "09:00"
            end_time = "14:00"
            
            # "9①14" のような表記から時間を抽出
            m_match = re.search(r'(\d+)\s*[①-⑨]\s*(\d+)', sub_info)
            if m_match:
                start_time = f"{int(m_match.group(1)):02d}:00"
                end_time = f"{int(m_match.group(2)):02d}:00"
                
            events.append(["本町", target_date, start_time, target_date, end_time, "False", "", "本町", "False"])
            
        # (2) それ以外 (time_scheduleになく、本町でもない。例:休、有休)
        else:
            events.append([info, target_date, "", target_date, "", "True", "", "", "False"])

    return events

def create_and_upload_calendar_csv(drive_service, folder_id, y, m, location, my_shift, time_schedule):
    """Google DriveへのCSVアップロード"""
    events = create_calendar_csv_data(y, m, location, my_shift, time_schedule)
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerows(events)
    
    filename = f"{y:04d}年{m:02d}月_シフトカレンダー.csv"
    file_metadata = {'name': filename, 'parents': [folder_id]}
    media = MediaIoBaseUpload(io.BytesIO(output.getvalue().encode('utf-8-sig')), mimetype='text/csv')
    
    file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    return filename, file.get('id')
