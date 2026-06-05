import pandas as pd

def load_master_from_sheets():
    """
    [1] 時程表読込（画面表示なし）
    A列を勤務地(Key)として辞書を作成。
    """
    # 実際のファイル名に合わせて指定してください
    df = pd.read_csv("時程表.xlsx - Table 1.csv", encoding="shift_jis")
    
    time_dic = {}
    # A列(iloc[:, 0])を勤務地としてグループ化して辞書に格納
    for location, group in df.groupby(df.iloc[:, 0]):
        time_dic[str(location).strip()] = group
    return time_dic

def register_shift_data(df, target_staff, location, time_dic):
    """
    [2] 抽出ロジック
    指定スタッフの2行を抽出 ＋ 他スタッフ（人名行のみ）を抽出
    """
    # 勤務地キーで時程表を取得
    target_time_schedule = time_dic.get(location, pd.DataFrame())
    
    # 指定スタッフの行を見つける
    staff_rows = df[df.iloc[:, 0] == target_staff]
    
    # 人名行抽出用フィルタ：不要な行（日付、曜日、勤務地コード、空行）を排除
    def is_staff_row(row):
        val = str(row[0]).strip()
        # 除外するキーワードリスト
        exclude = ['T1', 'T2', 'シフトコード', '1', '2', '3', '4', '木', '金', '土', '日', '月', '火', '水', 'nan', '']
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
    
    # my_daily_shift: 名前行 + その直下の行（2行セット）
    my_daily_shift = df.iloc[idx : idx + 2]
    
    return {
        "my_daily_shift": my_daily_shift,
        "other_daily_shift": other_df,
        "time_schedule": target_time_schedule
    }
