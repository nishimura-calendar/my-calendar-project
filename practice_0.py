import pandas as pd
import camelot
import re
import calendar

def load_and_validate_pdf(pdf_path, year, month, time_dic):
    """
    [2] PDF読み込みと検証（第1関門・第2関門）
    """
    # 1. camelotで読み込み
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    df = tables[0].df
    
    # 2. [0,0]セルから勤務地(C)を抽出
    raw_header = str(df.iloc[0, 0])
    # 日付・曜日・不要な記号を除去し、英数字を維持する
    location_candidate = re.sub(r'[\s\u4e00-\u9fff/年月日時曜日]', '', raw_header).strip()
    
    # 3. 第2関門: 時程表のキーとの照合
    matched_location = None
    for key in time_dic.keys():
        if key == location_candidate:
            matched_location = key
            break
            
    if not matched_location:
        return None, f"勤務地不一致: {location_candidate}", None
        
    return df, "通過", matched_location

def extract_target_data(df, target_staff, location, time_dic):
    """スタッフデータの抽出"""
    # 0列目を走査してスタッフ名を探す
    if target_staff not in df.iloc[:, 0].values:
        return None
    
    idx = df[df.iloc[:, 0] == target_staff].index[0]
    
    # 抽出結果を辞書で返す
    return {
        "time_schedule": time_dic[location],
        "my_daily_shift": df.iloc[idx : idx+1],
        "other_daily_shift": df.drop(index=idx)
    }
