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

def analyze_pdf_structure(pdf_path, y, m):
    """第1・第2関門およびデータ抽出"""
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    if not tables: return None, "PDF表抽出失敗"
    df = tables[0].df
    
    raw_0_0 = str(df.iloc[0, 0]).replace('\n', ' ').strip()
    
    # 第1関門チェック
    calc_last_day, calc_first_w = get_calc_date_info(y, m)
    nums = [int(n) for n in re.findall(r'\d+', raw_0_0)]
    pdf_last_day = max(nums) if nums else 0
    pdf_first_w = (re.findall(r'[月火水木金土日]', raw_0_0) + [""])[0]
    
    if not (pdf_last_day == calc_last_day and pdf_first_w == calc_first_w):
        return None, f"不一致：算出={calc_last_day}({calc_first_w}) / PDF={pdf_last_day}({pdf_first_w})"

    # location特定
    loc_tmp = re.sub(r'[月火水木金土日]', '', raw_0_0)
    loc_tmp = re.sub(r'\d+年\d+月度|勤務予定表|～|~|-|－|：|:', '', loc_tmp)
    loc_tmp = re.sub(r'\b\d{1,2}\b', '', loc_tmp)
    location = re.sub(r'\s+', '', loc_tmp).strip()
    
    # スタッフリスト作成
    staff_names = []
    for i in range(2, len(df), 2):
        name = str(df.iloc[i, 0]).split('\n')[0].strip()
        if name and name != location:
            staff_names.append(name)
            
    return {"df": df, "location": location, "staff_list": staff_names}, "成功"

def get_last_name(full_name):
    """フルネームから名字のみを抽出"""
    return re.split(r'[\s　]+', str(full_name).strip())[0]

def parse_time_from_detail(detail):
    """工程6：下段(詳細)から時間を抽出 (例: 9①14 -> 09:00, 14:00)"""
    match = re.search(r'(\d{1,2})[①-⑩](\d{1,2})', str(detail))
    if match:
        return f"{int(match.group(1)):02d}:00", f"{int(match.group(2)):02d}:00"
    return "", ""

def shift_cal(key, target_date, col_idx, shift_info, detail, other_staff_shift, time_schedule, final_rows):
    """メイン工程：通常シフト・他拠点・休日の判定と計算"""
    last_name_me = get_last_name(key)
    
    # 休日関係
    if any(x in shift_info for x in ["休", "公休", "有給", "有休", "特休"]):
        final_rows.append([f"{last_name_me}_{shift_info}", target_date, "", target_date, "", "True", "", ""])
        return

    # 他拠点（本町）対応：工程6
    if "本町" in detail or "本町" in shift_info:
        s_time, e_time = parse_time_from_detail(detail)
        final_rows.append([f"{last_name_me}_本町", target_date, s_time, target_date, e_time, "False", f"詳細:{detail}", ""])
        return

    # 通常シフト（時程表にコードがある場合）
    time_shift = time_schedule.fillna("").astype(str)
    if (time_shift.iloc[:, 1] == shift_info).any():
        final_rows.append([f"{last_name_me}_{shift_info}", target_date, "", target_date, "", "True", "", ""])
        
        my_time_shift = time_shift[time_shift.iloc[:, 1] == shift_info]
        prev_val = ""
        for t_col in range(2, my_time_shift.shape[1]):
            current_val = my_time_shift.iloc[0, t_col]
            if current_val != prev_val:
                if current_val != "":
                    # 引き継ぎ相手の特定（名字のみ）
                    valid_codes = time_shift[time_shift.iloc[:, t_col] == current_val].iloc[:, 1].tolist()
                    others = []
                    for _, row in other_staff_shift.iterrows():
                        if str(row[col_idx]).strip() in valid_codes:
                            others.append(get_last_name(row[0]))
                    
                    staff_str = ",".join([n for n in others if n != last_name_me]) or "なし"
                    subject = f"<{current_val}> {last_name_me}=>{staff_str}"
                    final_rows.append([subject, target_date, time_shift.iloc[0, t_col], target_date, "", "False", "", ""])
                else:
                    # 終了処理（退勤判定）
                    if final_rows:
                        suffix = " => (退勤)" if (my_time_shift.iloc[0, t_col:] == "").all() else ""
                        final_rows[-1][0] += suffix
                        final_rows[-1][4] = time_shift.iloc[0, t_col]
            prev_val = current_val
