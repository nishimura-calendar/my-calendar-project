import pandas as pd

def load_master_from_sheets():
    """
    [1] 時程表読込
    A列を勤務地（Key）として辞書を生成。表示は一切行わない。
    """
    # 実際のファイルパスに合わせて修正してください
    df = pd.read_csv("時程表.xlsx - Table 1.csv")
    
    time_dic = {}
    # A列(iloc[:, 0])を勤務地としてグループ化
    for location, group in df.groupby(df.iloc[:, 0]):
        # キーの前後の空白を除去して辞書登録
        time_dic[str(location).strip()] = group
    return time_dic

def register_shift_data(df, target_staff, location, time_dic):
    """
    [2] 抽出ロジック
    """
    # 勤務地をキーに時程表を取得（なければ空DF）
    target_time_schedule = time_dic.get(location, pd.DataFrame())
    
    # 1. ターゲットスタッフの行を見つける
    staff_rows = df[df.iloc[:, 0] == target_staff]
    
    # 2. 人名行抽出用フィルター
    # 数値、T1/T2、曜日などが含まれる行を徹底的に除外する
    def is_staff_row(row):
        val = str(row[0]).strip()
        exclude = ['T1', 'T2', 'シフトコード', '1', '2', '木', '金', '土', '日', '月', '火', '水', 'nan', '']
        return val not in exclude and not val.isdigit()

    mask = df.apply(is_staff_row, axis=1)
    # 人名行のみ、かつ選択したスタッフ以外を抽出
    other_df = df[mask & (df.iloc[:, 0] != target_staff)]
    
    if staff_rows.empty:
        return {
            "my_daily_shift": pd.DataFrame(),
            "other_daily_shift": other_df,
            "time_schedule": target_time_schedule
        }
        
    idx = staff_rows.index[0]
    
    # my_daily_shift: 名前行 + 次の行（2行セット）
    my_daily_shift = df.iloc[idx : idx + 2]
    
    return {
        "my_daily_shift": my_daily_shift,
        "other_daily_shift": other_df,
        "time_schedule": target_time_schedule
    }
