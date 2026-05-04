import pandas as pd
import camelot
import re
import calendar
import math

def get_calc_date_info(y, m):
    """① ファイル名から算出する日数と第一曜日"""
    _, last_day = calendar.monthrange(y, m)
    w_list = ["月", "火", "水", "木", "金", "土", "日"]
    first_w = w_list[calendar.weekday(y, m, 1)]
    return last_day, first_w

def analyze_pdf_structure(pdf_path, y, m):
    """第一関門・データ抽出"""
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    if not tables: return None, "PDF表抽出失敗"
    df = tables[0].df
    raw_0_0 = str(df.iloc[0, 0]).strip()
    
    # ② ファイル内容[0,0]から月末日と第一曜日を抽出[cite: 9]
    nums = [int(n) for n in re.findall(r'\d+', raw_0_0)]
    pdf_last_day = max(nums) if nums else 0
    days_found = re.findall(r'[月火水木金土日]', raw_0_0)
    pdf_first_w = days_found[0] if days_found else ""
    
    calc_last_day, calc_first_w = get_calc_date_info(y, m)
    
    # 第一関門判定[cite: 9]
    if not (pdf_last_day == calc_last_day and pdf_first_w == calc_first_w):
        reason = f"不一致：計算={calc_last_day}({calc_first_w}) / PDF={pdf_last_day}({pdf_first_w})"
        return None, reason

    # ＜2＞ location抽出：日付の塊と曜日を「除去」して残りを取得[cite: 8, 9]
    # 1. 曜日(括弧含む)を除去
    location = re.sub(r'\(?[月火水木金土日]\)?', '', raw_0_0)
    # 2. 日付の塊 (例: 1～31, 1~31) を除去
    location = re.sub(r'\d+[\s～~-]+\d+', '', location)
    # 3. 単位や記号、端に残った数字を除去
    location = re.sub(r'[年月日で\s/：:-]', '', location).strip()
    
    # スタッフ名取得[cite: 9]
    staff_names = [str(df.iloc[i, 0]).split('\n')[0].strip() for i in range(2, len(df), 2) if str(df.iloc[i, 0]).strip()]
    
    # データ組替[cite: 9]
    rows = []
    rows.append([""] + df.iloc[0, 1:].tolist()) # [0,0]=""
    rows.append([location] + df.iloc[1, 1:].tolist()) # [1,0]=location
    for i in range(2, len(df)):
        cell = str(df.iloc[i, 0]).strip()
        name_val = cell.split('\n')[0] if i % 2 == 0 else cell
        rows.append([name_val] + df.iloc[i, 1:].tolist())
            
    return {"df": pd.DataFrame(rows), "location": location, "staff_list": staff_names}, "通過"
