import pandas as pd
import camelot
import re
import calendar

def get_calc_date_info(y, m):
    """① ファイル名から算出する日数と第一曜日[cite: 7]"""
    _, last_day = calendar.monthrange(y, m)
    w_list = ["月", "火", "水", "木", "金", "土", "日"]
    first_w = w_list[calendar.weekday(y, m, 1)]
    return last_day, first_w

# load_master_from_sheets, process_time_block は source 7 と同様のため維持

def analyze_pdf_structure(pdf_path, y, m):
    """第一関門判定・location抽出・データ組替[cite: 5, 7]"""
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    if not tables: return None, "PDF表抽出失敗"
    df = tables[0].df
    raw_0_0 = str(df.iloc[0, 0]).strip()
    
    # 第一関門判定[cite: 7]
    nums = [int(n) for n in re.findall(r'\d+', raw_0_0)]
    pdf_last_day = max(nums) if nums else 0
    pdf_first_w = re.findall(r'[月火水木金土日]', raw_0_0)[0] if re.findall(r'[月火水木金土日]', raw_0_0) else ""
    calc_last_day, calc_first_w = get_calc_date_info(y, m)
    
    if not (pdf_last_day == calc_last_day and pdf_first_w == calc_first_w):
        return None, "ファイル名とファイル内容に相違があります。確認して下さい。"

    # location抽出[cite: 7]
    loc = re.sub(r'\(?[月火水木金土日]\)?', '', raw_0_0)
    loc = re.sub(r'\d+[\s～~-]+\d+', '', loc)
    loc = re.sub(r'\b([1-9]|[12][0-9]|3[01])\b', '', loc)
    location = re.sub(r'[年月日で\s/：:-]', '', loc).strip()
    
    # 第3関門：スタッフ名リスト作成（locationと一致する場合は除外）[cite: 5]
    staff_names = []
    for i in range(2, len(df), 2):
        name = str(df.iloc[i, 0]).split('\n')[0].strip()
        if name and name != location: # locationと同一なら飛ばす
            staff_names.append(name)
    
    # データ組替[cite: 7]
    rows = []
    rows.append([""] + df.iloc[0, 1:].tolist()) # [0,0]=""
    rows.append([location] + df.iloc[1, 1:].tolist()) # [1,0]=location
    for i in range(2, len(df)):
        cell = str(df.iloc[i, 0]).strip()
        val = cell.split('\n')[0] if i % 2 == 0 else cell
        rows.append([val] + df.iloc[i, 1:].tolist())
            
    return {"df": pd.DataFrame(rows), "location": location, "staff_list": staff_names}, "通過"
