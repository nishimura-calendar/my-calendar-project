import pandas as pd
import os

def load_master_from_sheets():
    """
    [1] 時程表読込
    master.csvのA列を勤務地として辞書化。画面表示は行わない。
    """
    # 読み込み用パスの指定
    file_path = "master.csv"
    if not os.path.exists(file_path):
        return {}
    
    df = pd.read_csv(file_path, encoding="shift_jis")
    time_dic = {}
    for location, group in df.groupby(df.iloc[:, 0]):
        time_dic[str(location).strip()] = group
    return time_dic

def register_shift_data(df, target_staff, location, time_dic):
    """
    [2] 抽出ロジック
    my_daily_shift: 指定スタッフの2行
    other_daily_shift: 他スタッフの人名のみ
    time_schedule: 時程表マスタ
    """
    target_time_schedule = time_dic.get(location, pd.DataFrame())
    
    # 指定スタッフの行を見つける
    staff_rows = df[df.iloc[:, 0] == target_staff]
    
    # 人名行抽出用フィルタ：不要な行を除外
    def is_staff_row(row):
        val = str(row[0]).strip()
        exclude = ['T1', 'T2', 'シフトコード', '1', '2', '3', '4', '木', '金', '土', '日', '月', '火', '水', 'nan', '']
        return val not in exclude and not val.isdigit()

    mask = df.apply(is_staff_row, axis=1)
    other_df = df[mask & (df.iloc[:, 0] != target_staff)]
    
    my_daily_shift = df.iloc[staff_rows.index[0] : staff_rows.index[0] + 2] if not staff_rows.empty else pd.DataFrame()
    
    return {
        "my_daily_shift": my_daily_shift,
        "other_daily_shift": other_df,
        "time_schedule": target_time_schedule
    }
