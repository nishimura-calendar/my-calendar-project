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
        res = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=f"'{title}'!A1:Z300"
        ).execute()
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
    """時程データの数値時間変換（小数時間をHH:MM形式へ）"""
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
    """第1・第2関門の判定"""
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    if not tables: return None, "PDF表の抽出に失敗しました。"
    df = tables[0].df
    raw_0_0 = str(df.iloc[0, 0]).replace('\n', ' ').strip()
    
    # --- 第1関門 ---
    calc_last_day, calc_first_w = get_calc_date_info(y, m)
    nums = [int(n) for n in re.findall(r'\d+', raw_0_0)]
    pdf_last_day = max(nums) if nums else 0
    pdf_first_w = (re.findall(r'[月火水木金土日]', raw_0_0) + [""])[0]
    
    if not (pdf_last_day == calc_last_day and pdf_first_w == calc_first_w):
        return None, f"第1関門不通過：ファイル名と内容に相違があります（算出={calc_last_day}{calc_first_w}/PDF={pdf_last_day}{pdf_first_w}）"

    # --- 第2関門 ---
    location = re.sub(r'[月火水木金土日\d年 月度勤務予定表～~\-－：:\s]', '', raw_0_0).strip()
    
    staff_names = []
    for i in range(2, len(df), 2):
        name = str(df.iloc[i, 0]).split('\n')[0].strip()
        if name and name != location:
            staff_names.append(name)
            
    return {"df": df, "location": location, "staff_list": staff_names}, "通過"

def extract_target_data(df, target_staff, location):
    """第3関門：target_staffの検索とデータ抽出"""
    if target_staff not in df[0].values:
        return None
    idx = df[df[0] == target_staff].index[0]
    my_daily_shift = df.iloc[idx : idx+2, :].copy()
    other_indices = [i for i in range(2, len(df)) if i != idx and i != (idx + 1) and str(df.iloc[i, 0]).strip() not in ["", location]]
    other_daily_shift = df.iloc[other_indices, :].copy()
    return {"my_daily_shift": my_daily_shift, "other_daily_shift": other_daily_shift}

# --- メイン工程用ロジック ---

def get_last_name(full_name):
    """フルネームから名字のみ抽出"""
    if not full_name: return ""
    return re.split(r'[\s　]+', str(full_name).strip())[0]

def parse_honmachi_time(detail):
    """工程6：本町時間抽出（9①14 -> 09:00, 14:00）"""
    match = re.search(r'(\d{1,2})[①-⑩](\d{1,2})', str(detail))
    if match:
        return f"{int(match.group(1)):02d}:00", f"{int(match.group(2)):02d}:00"
    return "", ""

def shift_cal(key_name, target_date, col_idx, shift_info, other_staff_shift, time_schedule, final_rows):
    """通常シフトの時間別引き継ぎ計算"""
    time_shift = time_schedule.fillna("").astype(str)
    my_time_shift = time_shift[time_shift.iloc[:, 1] == shift_info]
    
    if not my_time_shift.empty:
        prev_val = ""
        for t_col in range(2, my_time_shift.shape[1]):
            current_val = my_time_shift.iloc[0, t_col]
            if current_val != prev_val:
                if current_val != "":
                    valid_codes = time_shift[time_shift.iloc[:, t_col] == current_val].iloc[:, 1].tolist()
                    names = [get_last_name(r[0]) for _, r in other_staff_shift.iterrows() if str(r[col_idx]).strip() in valid_codes]
                    staff_str = ",".join([n for n in names if n != key_name]) or "なし"
                    final_rows.append([f"<{current_val}> {key_name}=>{staff_str}", target_date, time_shift.iloc[0, t_col], target_date, "", "False", "", ""])
                else:
                    if final_rows:
                        final_rows[-1][0] += " => (退勤)" if (my_time_shift.iloc[0, t_col:] == "").all() else ""
                        final_rows[-1][4] = time_shift.iloc[0, t_col]
            prev_val = current_val
