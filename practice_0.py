import pandas as pd
import camelot
import re
import calendar

# (既存の get_calc_date_info, load_master_from_sheets, process_time_block は変更なし)

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
    rows.append([""] + df.iloc[0, 1:].tolist()) # [0,0]=""
    rows.append([location] + df.iloc[1, 1:].tolist()) # [1,0]=location
    
    staff_names = []
    for i in range(2, len(df)):
        cell = str(df.iloc[i, 0]).strip()
        val = cell.split('\n')[0] if i % 2 == 0 else cell
        rows.append([val] + df.iloc[i, 1:].tolist())
        
        # 氏名一覧：[2,0]から1行おき、locationと一致せず、かつ空でないもの
        if i % 2 == 0 and val and val != location:
            staff_names.append(val)
            
    return {"df": pd.DataFrame(rows), "location": location, "staff_list": staff_names}, "通過"

def extract_target_data(df, target_staff, location):
    """第3関門：my_daily_shift, other_daily_shiftの抽出"""
    # target_staff検索
    if target_staff not in df[0].values:
        return None
        
    idx = df[df[0] == target_staff].index[0]
    
    # my_daily_shift: target_staff行 + その下段（資格行）
    my_daily_shift = df.iloc[idx : idx+2, :].copy()
    
    # other_daily_shift: target_staff以外、location以外、かつ空白行以外
    # 0,1行目（日付/曜日）を除いた2行目以降から抽出
    other_indices = []
    for i in range(2, len(df)):
        val_0 = str(df.iloc[i, 0]).strip()
        # 条件：自分ではない かつ locationではない かつ 空白ではない
        if i != idx and i != (idx + 1) and val_0 != location and val_0 != "":
            other_indices.append(i)
            
    other_daily_shift = df.iloc[other_indices, :].copy()
    
    return {
        "my_daily_shift": my_daily_shift,
        "other_daily_shift": other_daily_shift
    }
