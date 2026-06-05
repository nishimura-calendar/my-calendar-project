import pandas as pd
import camelot
import re

def load_master_from_sheets():
    """[1] 時程表読み込み（実データ読み込み処理を想定）"""
    # ここに実際のCSV読み込みを記述してください
    # 例: df = pd.read_csv("master.csv")
    # 検証用：以下のような辞書を生成してください
    time_dic = {
        "T1": pd.DataFrame({'Code': ['J', 'A', 'F'], 'Start': ['09:00', '10:00', '13:00']}),
        "T2": pd.DataFrame({'Code': ['J', 'A', 'F'], 'Start': ['08:00', '09:00', '12:00']})
    }
    return time_dic

def register_shift_data(df, target_staff, location, time_dic):
    """[2] 抽出ロジック（time_scheduleの紐付けを強化）"""
    staff_rows = df[df.iloc[:, 0] == target_staff]
    
    # 勤務地が辞書にあるか確認
    target_time_schedule = time_dic.get(location, pd.DataFrame())
    
    if target_staff == "該当者なし" or staff_rows.empty:
        return {
            "my_daily_shift": pd.DataFrame(),
            "other_daily_shift": df[df.iloc[:, 0].notnull()], # 人名行のみ
            "time_schedule": target_time_schedule
        }
        
    idx = staff_rows.index[0]
    
    # my_daily_shift: 名前行 + その下の行
    my_daily_shift = df.iloc[idx : idx + 2]
    
    # other_daily_shift: 名前行のみを抽出（日付行などは除外）
    # 名前列(0列目)が空でない行かつ、選択スタッフではない行
    other_indices = [i for i in range(len(df)) if i != idx and str(df.iloc[i, 0]).strip() != ""]
    other_daily_shift = df.iloc[other_indices]
    
    return {
        "my_daily_shift": my_daily_shift,
        "other_daily_shift": other_daily_shift,
        "time_schedule": target_time_schedule
    }
