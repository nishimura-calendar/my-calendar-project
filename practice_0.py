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

def analyze_pdf_structure(pdf_path, y, m):
    """第一関門・データ抽出"""
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

    # location抽出
    location = re.sub(r'\(?[月火水木金土日]\)?', '', raw_0_0)
    location = re.sub(r'\d+[\s～~-]+\d+', '', location)
    location = re.sub(r'\b([1-9]|[12][0-9]|3[01])\b', '', location)
    location = re.sub(r'[年月日で\s/：:-]', '', location).strip()
    
    # データ組替とスタッフリスト作成
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
    """第3関門：my_daily_shift, other_daily_shiftの抽出"""
    if target_staff not in df[0].values:
        return None
        
    idx = df[df[0] == target_staff].index[0]
    
    # my_daily_shift: target_staff行 + その下段（資格行）
    my_daily_shift = df.iloc[idx : idx+2, 1:]
    
    # other_daily_shift: 自分以外のスタッフ行をすべて結合（2行セットずつ）
    other_rows = []
    for i in range(2, len(df), 2):
        s_name = df.iloc[i, 0]
        if s_name != target_staff and s_name != location and s_name != "":
            other_rows.append(df.iloc[i:i+2, :])
            
    other_daily_shift = pd.concat(other_rows) if other_rows else pd.DataFrame()
    
    return {
        'my_daily_shift': my_daily_shift,
        'other_daily_shift': other_daily_shift
    }

# --- ここから新規実装：[3] カレンダー自動生成ロジック（⑥までの他スタッフマスク動調対応） ---
def generate_calendar_records(year, month, location, time_schedule_df, my_daily_shift_df, other_staff_shift_df):
    """[3] プログラム作成手順に基づくカレンダー自動生成（⑥まで対応版）"""
    final_rows = []
    time_shift = time_schedule_df.fillna("").astype(str)
    
    # my_daily_shift_dfの各列（日付列）を1日から順に走査
    for col_idx in my_daily_shift_df.columns:
        try:
            day_num = int(col_idx)
        except ValueError:
            continue
            
        target_date = f"{year}/{month:02d}/{day_num:02d}"
        
        # 該当日の上段（勤務記号）と下段（資格・休憩）
        info = str(my_daily_shift_df.iloc[0, col_idx-1]).strip()
        sub_info = str(my_daily_shift_df.iloc[1, col_idx-1]).strip()
        
        # 修正指示反映：”なし”および"なし"の時は空文字として扱う
        if info == "なし": info = ""
        if sub_info == "なし": sub_info = ""
        
        # 休日判定（スキップ処理）
        if info in ["休", "休日", "公休", "有給", "有休", "他", ""]:
            continue
            
        # 1. 「本町」の場合の特例処理
        if info == "本町":
            final_rows.append(["本町", target_date, "", target_date, "", "True", "1行上=本町", "本町"])
            maru = re.findall(r'[①-⑨]', sub_info)
            desc_val = f"休憩={maru[0]}" if maru else ""
            final_rows.append(["本町", target_date, "09:00", target_date, "14:00", "False", desc_val, "本町"])
            continue
            
        # 2. 通常シフト（時程表に勤務記号の一致がある場合）
        if (time_shift.iloc[:, 1] == info).any():
            # 終日予定予定行（例: T2_A）を追加
            final_rows.append([f"{location}_{info}", target_date, "", target_date, "", "True", "", ""])
            
            my_time_shift = time_shift[time_shift.iloc[:, 1] == info]
            if not my_time_shift.empty:
                prev_val = ""
                added_sub_row = False
                
                # 時程表の3列目（時刻ヘッダー列）以降をスキャン
                for t_col in range(3, my_time_shift.shape[1]):
                    current_val = my_time_shift.iloc[0, t_col]
                    if current_val == "なし": current_val = ""
                    if current_val == prev_val:
                        continue
                        
                    current_time = my_time_shift.columns[t_col]
                    
                    if current_val != "":
                        taking_over_department = f"<{current_val}>"
                        taking_over_staff = ""
                        
                        # ⑥ 同一時間・同一部署にいる他スタッフをother_daily_shiftからマスク抽出
                        if not other_staff_shift_df.empty:
                            other_upper_rows = other_staff_shift_df.iloc[::2] # 上段行（記号行）のみを対象
                            if col_idx <= other_upper_rows.shape[1]:
                                mask_other_col = other_upper_rows.iloc[:, col_idx] == current_val
                                other_names = other_upper_rows[mask_other_col].iloc[:, 0].tolist()
                                if other_names:
                                    taking_over_staff = f"with {','.join(other_names)}"
                                
                        handing_over_department = ""
                        if prev_val != "":
                            handing_over_department = f"<{prev_val}>"
                            
                        handing_over_staff = ""
                        if prev_val != "" and (time_shift.iloc[:, 1] == prev_val).any():
                            mask_handing_dept = time_shift.iloc[:, 1] == prev_val
                            mask_handing_codes = time_shift.loc[mask_handing_dept, time_shift.columns[1]]
                            
                            if not other_staff_shift_df.empty:
                                other_upper_rows = other_staff_shift_df.iloc[::2]
                                mask_trans_handing = other_upper_rows.iloc[:, col_idx].isin(mask_handing_codes)
                                handing_over_names = other_upper_rows[mask_trans_handing].iloc[:, 0].tolist()
                                handing_over_staff = f"to {','.join(handing_over_names)}" if handing_over_names else ""
                        
                        subject_raw = f"{handing_over_department} {handing_over_staff}=>{taking_over_department} {taking_over_staff}"
                        subject = re.sub(r'\s+', ' ', subject_raw).strip()
                        
                        if added_sub_row and len(final_rows) > 0:
                            final_rows[-1][4] = current_time  
                            
                        final_rows.append([subject, target_date, current_time, target_date, "", "False", "", ""])
                        added_sub_row = True
                        prev_val = current_val
                    else:
                        # 退勤の判定
                        if added_sub_row and len(final_rows) > 0:
                            final_rows[-1][4] = current_time  
                            remaining_cells = my_time_shift.iloc[0, t_col:]
                            if (remaining_cells == "").all() or (remaining_cells == "0").all() or (remaining_cells == "なし").all():
                                taking_over_department = " => (退勤)"
                            else:
                                taking_over_department = ""
                                
                            final_rows[-1][0] = final_rows[-1][0] + taking_over_department
                            added_sub_row = False
                        prev_val = ""

                if added_sub_row and len(final_rows) > 0 and final_rows[-1][4] == "":
                    final_rows[-1][4] = my_time_shift.columns[-1]

    return pd.DataFrame(final_rows, columns=["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location"])
