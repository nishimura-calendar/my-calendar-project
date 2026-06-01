import pandas as pd
import camelot
import re
import calendar

def get_calc_date_info(y, m):
    """A：取得した年月から算出する最終日付（日数）と最終曜日を取得する"""
    _, last_day = calendar.monthrange(y, m)
    w_list = ["月", "火", "水", "木", "金", "土", "日"]
    last_w = w_list[calendar.weekday(y, m, last_day)]
    return last_day, last_w

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
    """第1関門：仕様(2)に基づき、1行目の日付文字列全体から月末日・末尾曜日を厳密に特定する"""
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    if not tables: return None, "PDF表抽出失敗"
    df = tables[0].df
    
    # A：取得した年月から算出する最終日付と最終曜日
    calc_last_day, calc_last_w = get_calc_date_info(y, m)
    
    # B：詠込んだpdfシフト表ファイルから最終日付と最終曜日を取得する
    pdf_last_day = 0
    pdf_last_w = ""
    target_col_idx = -1
    
    # 仕様(2)より、行0は1〜月末までの日付文字列。
    # 各セルから数値をすべて抽出し、その中で「最大の数値」を月末日として特定する
    for col_idx in range(1, df.shape[1]):
        cell_text = str(df.iloc[0, col_idx]).strip()
        days_in_cell = [int(d) for d in re.findall(r'\d+', cell_text)]
        if days_in_cell:
            max_day_in_cell = max(days_in_cell)
            if max_day_in_cell > pdf_last_day:
                pdf_last_day = max_day_in_cell
                target_col_idx = col_idx

    # 月末日が見つかった列の、行1（曜日行）から末尾の曜日を取得する
    if target_col_idx != -1:
        combined_text = str(df.iloc[0, target_col_idx]) + " " + str(df.iloc[1, target_col_idx])
        weeks_found = re.findall(r'[月火水木金土日士]', combined_text)
        if weeks_found:
            pdf_last_w = weeks_found[-1]
            if pdf_last_w == "士":
                pdf_last_w = "土"

    # A=Bならそのまま通過、A≠Bなら不一致エラー
    if not (pdf_last_day == calc_last_day and pdf_last_w == calc_last_w):
        return None, f"不一致：計算上の月末={calc_last_day}日({calc_last_w}) ／ PDFの末尾={pdf_last_day}日({pdf_last_w})"

    # [0,0]近辺から勤務地(location)を抽出
    raw_0_0 = str(df.iloc[0, 0]).strip()
    if raw_0_0 == "" or len(raw_0_0) <= 2:
        raw_0_0 = str(df.iloc[1, 0]).strip()
        
    location = re.sub(r'\(?[月火水木金土日士]\)?', '', raw_0_0)
    location = re.sub(r'\d+[\s～~-]+\d+', '', location)
    location = re.sub(r'\b([1-9]|[12][0-9]|3[01])\b', '', location)
    location = re.sub(r'[年月日で\s/：:-]', '', location).strip()
    
    # 内部処理用データ構造への組み替え
    rows = []
    rows.append([""] + df.iloc[0, 1:].tolist()) 
    rows.append([location] + df.iloc[1, 1:].tolist())
    
    staff_names = []
    for i in range(2, len(df)):
        cell = str(df.iloc[i, 0]).strip()
        val = cell.split('\n')[0] if i % 2 == 0 else cell
        rows.append([val] + df.iloc[i, 1:].tolist())
        
        if i % 2 == 0 and val and val != location and not re.search(r'警備隊|株式会社', val):
            staff_names.append(val)
            
    return {"df": pd.DataFrame(rows), "location": location, "staff_list": staff_names}, "通過"

def extract_target_data(df, target_staff, location):
    """第3関門：my_daily_shift（2行）, other_daily_shift（各1行）の抽出"""
    if target_staff not in df[0].values:
        return None
        
    idx = df[df[0] == target_staff].index[0]
    my_daily_shift = df.iloc[idx : idx+2, 1:].copy()
    
    other_indices = []
    for i in range(2, len(df), 2):
        val_0 = str(df.iloc[i, 0]).strip()
        if i != idx and val_0 != location and val_0 != "" and not re.search(r'警備隊|株式会社', val_0):
            other_indices.append(i)
            
    other_daily_shift = df.iloc[other_indices, :].copy()
    
    return {
        "my_daily_shift": my_daily_shift,
        "other_daily_shift": other_daily_shift
    }

def generate_calendar_records(year, month, location, time_schedule_df, my_daily_shift_df, other_staff_shift_df):
    """[3] カレンダー登録用データの自動生成（構文エラー修正版）"""
    final_rows = []
    time_shift = time_schedule_df.fillna("").astype(str)
    
    for col_idx in my_daily_shift_df.columns:
        try:
            day_num = int(col_idx)
        except ValueError:
            continue
            
        target_date = f"{year}/{month:02d}/{day_num:02d}"
        
        info = str(my_daily_shift_df.iloc[0, col_idx-1]).strip()
        sub_info = str(my_daily_shift_df.iloc[1, col_idx-1]).strip()
        
        if info == "なし": info = ""
        if sub_info == "なし": sub_info = ""
        
        if info in ["休", "休日", "公休", "有給", "有休", "他", ""]:
            continue
            
        if info == "本町":
            final_rows.append(["本町", target_date, "", target_date, "", "True", "1行上=本町", "本町"])
            maru = re.findall(r'[①-⑨]', sub_info)
            desc_val = f"休憩={maru[0]}" if maru else ""
            final_rows.append(["本町", target_date, "09:00", target_date, "14:00", "False", desc_val, "本町"])
            continue
            
        if (time_shift.iloc[:, 1] == info).any():
            final_rows.append([f"{location}_{info}", target_date, "", target_date, "", "True", "", ""])
            
            my_time_shift = time_shift[time_shift.iloc[:, 1] == info]
            if not my_time_shift.empty:
                prev_val = ""
                added_sub_row = False
                
                for t_col in range(3, my_time_shift.shape[1]):
                    current_val = my_time_shift.iloc[0, t_col]
                    if current_val == "なし": current_val = ""
                    if current_val == prev_val:
                        continue
                        
                    current_time = my_time_shift.columns[t_col]
                    
                    if current_val != "":
                        taking_over_department = f"<{current_val}>"
                        taking_over_staff = ""
                        
                        if not other_staff_shift_df.empty:
                            if col_idx < other_staff_shift_df.shape[1]:
                                mask_other_col = other_staff_shift_df.iloc[:, col_idx] == current_val
                                other_names = other_staff_shift_df[mask_other_col].iloc[:, 0].tolist()
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
                                mask_trans_handing = other_staff_shift_df.iloc[:, col_idx].isin(mask_handing_codes)
                                handing_over_names = other_staff_shift_df[mask_trans_handing].iloc[:, 0].tolist()
                                handing_over_staff = f"to {','.join(handing_over_names)}" if handing_over_names else ""
                        
                        subject_raw = f"{handing_over_department} {handing_over_staff}=>{taking_over_department} {taking_over_staff}"
                        subject = re.sub(r'\s+', ' ', subject_raw).strip()
                        
                        if added_sub_row and len(final_rows) > 0:
                            final_rows[-1][4] = current_time  
                            
                        final_rows.append([subject, target_date, current_time, target_date, "", "False", "", ""])
                        added_sub_row = True
                        prev_val = current_val
                    else:
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
