import pandas as pd
import camelot
import re
import calendar

def get_calc_date_info(y, m):
    """① ファイル名から算出する日数と第一曜日[cite: 5]"""
    _, last_day = calendar.monthrange(y, m)
    w_list = ["月", "火", "水", "木", "金", "土", "日"]
    first_w = w_list[calendar.weekday(y, m, 1)]
    return last_day, first_w

def analyze_pdf_structure(pdf_path, y, m):
    """第一関門判定・location抽出・データ構造化"""
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    if not tables: return None, "PDF表抽出失敗"
    df = tables[0].df
    raw_0_0 = str(df.iloc[0, 0]).strip()
    
    # --- 第一関門判定 ---
    nums = [int(n) for n in re.findall(r'\d+', raw_0_0)]
    pdf_last_day = max(nums) if nums else 0
    days_found = re.findall(r'[月火水木金土日]', raw_0_0)
    pdf_first_w = days_found[0] if days_found else ""
    calc_last_day, calc_first_w = get_calc_date_info(y, m)
    
    if not (pdf_last_day == calc_last_day and pdf_first_w == calc_first_w):
        return None, "ファイル名とファイル内容に相違があります。確認して下さい。"

    # --- ＜2＞ location抽出（汎用ロジック） ---[cite: 9]
    # 曜日、日付（範囲）、単体日付、年月記号を除去して勤務地名を特定
    loc = re.sub(r'\(?[月火水木金土日]\)?', '', raw_0_0)
    loc = re.sub(r'\d+[\s～~-]+\d+', '', loc)
    loc = re.sub(r'\b([1-9]|[12][0-9]|3[01])\b', '', loc)
    location = re.sub(r'[年月日で\s/：:-]', '', loc).strip()
    
    # --- 第3関門：氏名一覧の作成 ---[cite: 9]
    # [2,0]から1行おきにリスト化。locationと同じ名前は除外。
    staff_names = []
    for i in range(2, len(df), 2):
        name = str(df.iloc[i, 0]).split('\n')[0].strip()
        if name and name != location:
            staff_names.append(name)
    
    # --- データ組替 ---[cite: 9]
    rows = []
    rows.append([""] + df.iloc[0, 1:].tolist()) 
    rows.append([location] + df.iloc[1, 1:].tolist()) 
    for i in range(2, len(df)):
        cell = str(df.iloc[i, 0]).strip()
        val = cell.split('\n')[0] if i % 2 == 0 else cell
        rows.append([val] + df.iloc[i, 1:].tolist())
            
    return {"df": pd.DataFrame(rows), "location": location, "staff_list": staff_names}, "通過"

# ※ load_master_from_sheets 等の他関数は既存通り[cite: 5]
