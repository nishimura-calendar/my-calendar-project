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
    """時程データの数値時間変換"""
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
    """第一・第二関門：構造解析と勤務地特定"""
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    if not tables: return None, "PDF表抽出失敗"
    df = tables[0].df
    raw_0_0 = str(df.iloc[0, 0]).replace('\n', ' ').strip()
    
    calc_last_day, calc_first_w = get_calc_date_info(y, m)
    nums = [int(n) for n in re.findall(r'\d+', raw_0_0)]
    pdf_last_day = max(nums) if nums else 0
    pdf_first_w = (re.findall(r'[月火水木金土日]', raw_0_0) + [""])[0]
    
    if not (pdf_last_day == calc_last_day and pdf_first_w == calc_first_w):
        return None, f"不一致：算出={calc_last_day}({calc_first_w}) / PDF={pdf_last_day}({pdf_first_w})"

    loc_tmp = re.sub(r'[月火水木金土日]', '', raw_0_0)
    loc_tmp = re.sub(r'\d+年\d+月度|勤務予定表|～|~|-|－|：|:', '', loc_tmp)
    loc_tmp = re.sub(r'\b\d{1,2}\b', '', loc_tmp)
    location = re.sub(r'\s+', '', loc_tmp).strip()
    
    staff_names = []
    for i in range(2, len(df), 2):
        name = str(df.iloc[i, 0]).split('\n')[0].strip()
        if name and name != location:
            staff_names.append(name)
            
    return {"df": df, "location": location, "staff_list": staff_names}, "成功"

def extract_target_data(df, target_staff, location):
    """第三関門：対象データの抽出"""
    if target_staff not in df[0].values: return None
    idx = df[df[0] == target_staff].index[0]
    my_daily_shift = df.iloc[idx : idx+2, :].copy()
    other_indices = [i for i in range(2, len(df)) if i != idx and i != (idx + 1) and str(df.iloc[i, 0]).strip() not in ["", location]]
    other_daily_shift = df.iloc[other_indices, :].copy()
    return {"my_daily_shift": my_daily_shift, "other_daily_shift": other_daily_shift}

# --- ここから＜プログラムのメイン工程＞用ロジック ---

def get_last_name(full_name):
    """氏名から名字のみを抽出（全角・半角スペース対応）"""
    if not full_name: return ""
    return re.split(r'[\s　]+', str(full_name).strip())[0]

def parse_honmachi_time(detail_text):
    """工程6：本町時間抽出（例：9①14 -> 9:00, 14:00）"""
    match = re.search(r'(\d{1,2})[①-⑩](\d{1,2})', str(detail_text))
    if match:
        return f"{int(match.group(1)):02d}:00", f"{int(match.group(2)):02d}:00"
    return "", ""

def shift_cal(key_name, target_date, col_idx, shift_info, other_staff_shift, time_schedule, final_rows):
    """通常シフトの詳細時間を計算しfinal_rowsに格納（名字表示対応）"""
    time_shift = time_schedule.fillna("").astype(str)
    my_time_shift = time_shift[time_shift.iloc[:, 1] == shift_info]
    
    if not my_time_shift.empty:
        prev_val = ""
        for t_col in range(2, my_time_shift.shape[1]):
            current_val = my_time_shift.iloc[0, t_col]
            if current_val != prev_val:
                if current_val != "":
                    # 引取相手の名字リスト作成
                    valid_codes = time_shift[time_shift.iloc[:, t_col] == current_val].iloc[:, 1].tolist()
                    names = [get_last_name(r[0]) for _, r in other_staff_shift.iterrows() if str(r[col_idx]).strip() in valid_codes]
                    staff_str = ",".join([n for n in names if n != key_name]) or "なし"
                    
                    final_rows.append([
                        f"<{current_val}> {key_name}=>{staff_str}", 
                        target_date, time_shift.iloc[0, t_col], target_date, "", "False", "", ""
                    ])
                else:
                    if final_rows:
                        # 退勤判定
                        suffix = " => (退勤)" if (my_time_shift.iloc[0, t_col:] == "").all() else ""
                        final_rows[-1][0] += suffix
                        final_rows[-1][4] = time_shift.iloc[0, t_col]
            prev_val = current_val

def run_main_process(y, m, final_result_dic):
    """メイン工程実行関数"""
    results = []
    for loc_key, data in final_result_dic.items():
        my_shift = data["my_daily_shift"]
        other_shift = data["other_daily_shift"]
        t_sched = data["time_schedule"]
        
        last_name_me = get_last_name(my_shift.iloc[0, 0])

        # 1列目(1日)から最終列まで巡回
        for col in range(1, my_shift.shape[1]):
            target_date = f"{y}/{m:02d}/{col:02d}"
            s_code = str(my_shift.iloc[0, col]).strip().replace('\n', '')
            d_info = str(my_shift.iloc[1, col]).strip().replace('\n', '')

            if not s_code or s_code == "なし": continue

            # 工程3: 分類
            # A. 休日関係 (赤)
            if any(x in s_code for x in ["休", "公休", "有給", "有休", "特休"]):
                results.append([f"{last_name_me}_{s_code}", target_date, "", target_date, "", "True", "", loc_key, "休日"])
            
            # B. 本町対応 (工程6 - 青)
            elif "本町" in s_code or "本町" in d_info:
                st_t, en_t = parse_honmachi_time(d_info)
                results.append([f"{last_name_me}_本町", target_date, st_t, target_date, en_t, "False", f"詳細:{d_info}", loc_key, "イベント"])
            
            # C. 通常シフト (時程表あり - 緑)
            elif (t_sched.iloc[:, 1] == s_code).any():
                results.append([f"{loc_key}_{s_code}", target_date, "", target_date, "", "True", "", loc_key, "key"])
                temp_rows = []
                shift_cal(last_name_me, target_date, col, s_code, other_shift, t_sched, temp_rows)
                for r in temp_rows:
                    results.append(r + [loc_key, "key"])
            
            # D. その他イベント (青)
            else:
                results.append([f"{last_name_me}_{s_code}", target_date, "", target_date, "", "True", f"詳細:{d_info}", loc_key, "イベント"])

    return pd.DataFrame(results, columns=["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location", "Type"])
