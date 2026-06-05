import pandas as pd
import camelot
import re

def load_master_from_sheets():
    """[1] 時程表読み込み（画面表示なし）"""
    # 実際はCSV等を読み込み、{ "T1": df1, ... } を返す
    return {"T1": pd.DataFrame()} 

def load_and_validate_pdf(pdf_path, time_dic):
    """[2] PDF読み込みと検証"""
    # camelotで読み込み
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    df = tables[0].df
    
    # 勤務地抽出
    raw_header = str(df.iloc[0, 0])
    location = re.sub(r'[\s\u4e00-\u9fff/年月日時曜日]', '', raw_header).strip()
    
    # 検証（辞書に存在するか）
    if location not in time_dic:
        return None, f"勤務地不一致: {location}", None
        
    return df, "通過", location

def register_shift_data(df, target_staff, location, time_dic):
    """[2] データ抽出ロジック"""
    # ターゲットスタッフの行番号を探す
    staff_rows = df[df.iloc[:, 0] == target_staff]
    
    # 勤務地から時程表を取得
    target_time_schedule = time_dic.get(location, pd.DataFrame())
    
    if target_staff == "該当者なし" or staff_rows.empty:
        return {
            "my_daily_shift": pd.DataFrame(),
            "other_daily_shift": df[df.iloc[:, 0].str.strip() != ""], # 人名行のみ
            "time_schedule": target_time_schedule
        }
        
    idx = staff_rows.index[0]
    
    # my_daily_shift: 名前行 + 直下の行（2行）
    my_daily_shift = df.iloc[idx : idx + 2]
    
    # other_daily_shift: 名前行のみを抽出
    # 0列目が空でなく、かつ選択したスタッフ名ではない行
    other_df = df[ (df.iloc[:, 0].str.strip() != "") & (df.iloc[:, 0] != target_staff) ]
    
    return {
        "my_daily_shift": my_daily_shift,
        "other_daily_shift": other_df,
        "time_schedule": target_time_schedule
    }
