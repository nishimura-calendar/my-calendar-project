import pandas as pd
import camelot
import re
import calendar

def load_and_validate_pdf(pdf_path, year, month):
    """[2] PDF読み込みと第1・第2関門チェック"""
    # 1. camelotで読み込み
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    df = tables[0].df
    
    # 2. [0,0]セルから勤務地(C)を抽出
    raw_header = str(df.iloc[0, 0])
    # 日付・曜日・空白を除去して勤務地だけ残す
    location = re.sub(r'[\d\s\u4e00-\u9fff/年月日時曜日]', '', raw_header)
    
    # 3. 第1関門: 年月のチェックロジック（簡易版）
    last_day, _ = calendar.monthrange(year, month)
    # ここにPDF内の最終日との比較ロジックを実装
    
    # 4. 第2関門: 勤務地照合
    # time_dicは事前に時程表から読み込まれている前提
    if location not in time_dic:
        return None, f"勤務地不一致: {location}"
        
    return df, "通過"

def extract_target_data(df, target_staff, location):
    """スタッフデータの抽出"""
    if target_staff not in df.iloc[:, 0].values:
        return None
    
    idx = df[df.iloc[:, 0] == target_staff].index[0]
    # my_daily_shiftとother_daily_shiftを抽出して返す
    return {
        "my_daily_shift": df.iloc[idx : idx+2], # 例
        "other_daily_shift": df.drop(index=idx)
    }
