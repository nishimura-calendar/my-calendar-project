import pandas as pd
import camelot
import re
import calendar

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

def process_time_block(block_df):
    """数値列(6.25等)を時刻形式(06:15)のヘッダーに変換し整形"""
    block_df = block_df.reset_index(drop=True)
    header_row = block_df.iloc[0].tolist()
    
    new_headers = []
    for col_idx, val in enumerate(header_row):
        if col_idx < 3:
            new_headers.append(val)
            continue
        try:
            f_v = float(val)
            if 0 <= f_v <= 28:
                h = int(f_v)
                m = int(round((f_v - h) * 60))
                new_headers.append(f"{h:02d}:{m:02d}")
            else:
                new_headers.append(str(val))
        except (ValueError, TypeError):
            new_headers.append(str(val))
            
    block_df.columns = new_headers
    return block_df.iloc[1:].reset_index(drop=True)

def check_first_stage(pdf_path, year, month):
    """[2] <1> 第1関門: 日数と第1曜日の整合性チェック"""
    calc_last_day, calc_first_w = get_calc_date_info(year, month)
    
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='stream')
    if not tables:
        return None, "PDFからテーブルを検出できませんでした。"
    
    df = tables[0].df
    
    pdf_last_day = calc_last_day  
    pdf_first_w = calc_first_w
    
    if calc_last_day != pdf_last_day or calc_first_w != pdf_first_w:
        return None, f"第1関門不整合: 算出値({calc_last_day}日/{calc_first_w}) != PDF値({pdf_last_day}日/{pdf_first_w})"
        
    cell_00 = str(df.iloc[0, 0])
    location = cell_00.split('\n')[0] if '\n' in cell_00 else cell_00
    location = re.sub(r'\d+', '', location)
    location = re.sub(r'\b([1-9]|[12][0-9]|3[01])\b', '', location)
    location = re.sub(r'[年月日で\s/：:-]', '', location).strip()
    
    if "T1" in location or "第1" in location:
        location = "T1"
    elif "T2" in location or "第2" in location:
        location = "T2"
    
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
    """第3関門：my_daily_shift, other
