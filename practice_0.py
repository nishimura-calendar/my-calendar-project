import pandas as pd
import camelot
import re
import calendar

def get_calc_date_info(y, m):
    """① ファイル名から算出する日数と第一曜日"""
    _, last_day = calendar.monthrange(y, m)
    # 0:月, 1:火, 2:水, 3:木, 4:金, 5:土, 6:日
    w_idx = calendar.weekday(y, m, 1)
    w_list = ["月", "火", "水", "木", "金", "土", "日"]
    first_w = w_list[w_idx]
    return last_day, first_w

def analyze_pdf_structure(pdf_path, y, m):
    """第1・第2関門：解析と照合"""
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    if not tables:
        return None, "PDFから表を抽出できませんでした。"
    
    df = tables[0].df
    raw_0_0 = str(df.iloc[0, 0]).replace('\n', ' ').strip()
    
    # --- 第1関門照合 ---
    calc_last_day, calc_first_w = get_calc_date_info(y, m)
    days_in_pdf = [int(n) for n in re.findall(r'\d+', raw_0_0)]
    pdf_last_day = max(days_in_pdf) if days_in_pdf else 0
    pdf_first_w_match = re.search(r'[月火水木金土日]', raw_0_0)
    pdf_first_w = pdf_first_w_match.group() if pdf_first_w_match else ""

    if pdf_last_day != calc_last_day or pdf_first_w != calc_first_w:
        return None, f"第1関門不通過: 算出={calc_last_day}{calc_first_w} / PDF={pdf_last_day}{pdf_first_w}"

    # --- 第2関門：location抽出 ---
    location = re.sub(r'[月火水木金土日]', '', raw_0_0)
    location = re.sub(r'\b(?:[1-9]|[12][0-9]|3[01])\b', '', location)
    location = re.sub(r'[年月日で\s/：:-]|勤務予定表|～|~', '', location).strip()
    
    # データ組替
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
    """第3関門：個人のシフト抽出"""
    if target_staff not in df[0].values:
        return None
    idx = df[df[0] == target_staff].index[0]
    my_daily_shift = df.iloc[idx : idx+2, :]
    other_daily_shift = df[(df.index >= 2) & (df.index % 2 == 0) & (df[0] != target_staff) & (df[0] != location)]
    return {"my_daily_shift": my_daily_shift, "other_daily_shift": other_daily_shift}

def execute_main_process(y, m, location, final_result, shift_cal_func):
    """
    <プログラムのメイン工程>
    1. keyを巡回
    2. my_daily_shiftを1列目から最終列まで巡回
    3. 各列の値を判定してshift_calを呼び出し
    """
    target_data = final_result.get(location)
    if not target_data:
        return []

    my_shift = target_data["my_daily_shift"]
    other_shift = target_data["other_daily_shift"]
    time_sched = target_data["time_schedule"]
    
    last_day, _ = get_calc_date_info(y, m)
    final_rows = []
    holidays = ["休日", "公休", "有給", "有休", "特休", "休"]

    # 2. 1列目(1日)から最終列まで巡回
    for day in range(1, last_day + 1):
        target_date = f"{y}-{m:02d}-{day:02d}"
        shift_info = str(my_shift.iloc[0, day]).strip()
        
        # 3. シフトコード判定
        is_holiday = any(h in shift_info for h in holidays) or shift_info == ""
        # 休日関係ならshift_info(休日等)をkeyに、そうでなければlocation(勤務地)をkeyに
        current_key = shift_info if is_holiday else location
            
        # shift_cal呼び出し (引数仕様を厳守)
        row_result = shift_cal_func(
            key=current_key,
            target_date=target_date,
            col=day,
            shift_info=shift_info,
            my_daily_shift=my_shift,
            other_staff_shift=other_shift,
            time_schedule=time_sched,
            final_rows=final_rows
        )
        final_rows.append(row_result)
        
    return final_rows
