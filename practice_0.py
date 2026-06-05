import pandas as pd
import camelot
import re
import calendar

def load_and_validate_pdf(pdf_path, year, month, time_dic):
    """[2] PDF読み込みと検証ロジック"""
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    df = tables[0].df
    
    # 勤務地(C)の抽出
    raw_header = str(df.iloc[0, 0])
    location = re.sub(r'[\d\s\u4e00-\u9fff/年月日時曜日]', '', raw_header).strip()
    
    # 第2関門：勤務地照合
    matched_location = None
    for key in time_dic.keys():
        if key == location:
            matched_location = key
            break
            
    if not matched_location:
        return None, f"勤務地不一致: {location}", None
        
    return df, "通過", matched_location

def extract_target_data(df, target_staff, location):
    """[2] <2>(3)④：シフトデータの抽出"""
    staff_rows = df[df.iloc[:, 0] == target_staff]
    if staff_rows.empty:
        return None
    
    idx = staff_rows.index[0]
    
    # my_daily_shift: 名前行(idx) + 直下の資格行(idx+1)
    my_daily_shift = df.iloc[idx : idx + 2]
    
    # other_daily_shift: 全ての「名前行(i)」のみを1行ずつ抽出
    other_indices = [i for i in range(len(df)) if i != idx and str(df.iloc[i, 0]).strip() != ""]
    other_daily_shift = df.iloc[other_indices]
    
    return {
        "my_daily_shift": my_daily_shift,
        "other_daily_shift": other_daily_shift
    }
