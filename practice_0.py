import pandas as pd
import camelot
import re
import calendar

def load_and_validate_pdf(pdf_path, year, month, time_dic):
    """
    [2] PDF読み込みとバリデーション
    """
    # 1. camelotで表を読み込み
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    df = tables[0].df
    
    # 2. [0,0]セルから勤務地(C)を抽出（日付・曜日を除去）
    raw_header = str(df.iloc[0, 0])
    location = re.sub(r'[\d\s\u4e00-\u9fff/年月日時曜日]', '', raw_header).strip()
    
    # 3. 第1関門: 年月のチェック
    # (ロジック実装箇所: ファイル名と中身の整合性)
    
    # 4. 第2関門: 勤務地照合
    if location not in time_dic:
        return None, f"勤務地不一致: {location}"
        
    return df, "通過"

def extract_target_data(df, target_staff, location, time_dic):
    """
    スタッフごとのシフトを抽出し、辞書形式で返す
    """
    if target_staff not in df.iloc[:, 0].values:
        return None
    
    idx = df[df.iloc[:, 0] == target_staff].index[0]
    
    return {
        "time_schedule": time_dic[location],
        "my_daily_shift": df.iloc[idx : idx+1],  # 個人行
        "other_daily_shift": df.drop(index=idx) # 他スタッフ行
    }
