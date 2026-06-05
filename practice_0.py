import pandas as pd
import camelot
import re

def load_and_validate_pdf(pdf_path, time_dic):
    """PDF読み込みと勤務地検証"""
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    df = tables[0].df
    
    # 勤務地抽出
    raw_header = str(df.iloc[0, 0])
    location = re.sub(r'[\s\u4e00-\u9fff/年月日時曜日]', '', raw_header).strip()
    
    # 勤務地照合
    if location not in time_dic:
        return None, f"勤務地不一致: {location}", None
        
    return df, "通過", location

def get_staff_list(df):
    """全てのスタッフ名リストを抽出（名前行のみ）"""
    # 2行目(インデックス2)以降から、名前列(0列目)が空でない行を取得
    # CSV構造に合わせて調整
    staff_list = df.iloc[2:, 0].dropna().astype(str).str.strip().tolist()
    return [name for name in staff_list if name != ""]

def extract_target_data(df, target_staff):
    """指定スタッフの行と直下の行を抽出"""
    # スタッフ名のインデックスを特定
    staff_rows = df[df.iloc[:, 0] == target_staff]
    if staff_rows.empty:
        return None
        
    idx = staff_rows.index[0]
    
    # my_daily_shift: 指定スタッフ行(idx) + 直下の行(idx+1)
    my_daily_shift = df.iloc[idx : idx + 2]
    
    # other_daily_shift: 他の全スタッフの名前行(1行ずつ)
    other_indices = [i for i in range(2, len(df)) if i != idx and str(df.iloc[i, 0]).strip() != ""]
    other_daily_shift = df.iloc[other_indices]
    
    return {
        "my_daily_shift": my_daily_shift,
        "other_daily_shift": other_daily_shift
    }
