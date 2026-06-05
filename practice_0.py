import pandas as pd
import camelot
import re

def load_master_from_sheets():
    """[1] 時程表読み込み（表示は行わない）"""
    # 実際はCSVやスプレッドシートから読み込む
    # ここでは仮に空の辞書を返しますが、必要に応じてCSVパスを指定してください
    time_dic = {"T1": pd.DataFrame(), "T2": pd.DataFrame()}
    return time_dic

def load_and_validate_pdf(pdf_path, time_dic):
    """[2] PDF読み込みと検証"""
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    df = tables[0].df
    
    raw_header = str(df.iloc[0, 0])
    location = re.sub(r'[\s\u4e00-\u9fff/年月日時曜日]', '', raw_header).strip()
    
    if location not in time_dic:
        return None, f"勤務地不一致: {location}", None
    return df, "通過", location

def get_staff_list(df):
    """スタッフ一覧取得（該当者なし含む）"""
    staff_list = df.iloc[2:, 0].dropna().astype(str).str.strip().unique().tolist()
    return ["該当者なし"] + [name for name in staff_list if name != ""]

def register_shift_data(df, target_staff, location, time_dic):
    """[2] 選択スタッフのデータ抽出・辞書化"""
    staff_rows = df[df.iloc[:, 0] == target_staff]
    
    if target_staff == "該当者なし" or staff_rows.empty:
        return {
            "my_daily_shift": pd.DataFrame(),
            "other_daily_shift": df,
            "time_schedule": time_dic.get(location, pd.DataFrame())
        }
        
    idx = staff_rows.index[0]
    return {
        "my_daily_shift": df.iloc[idx : idx + 2],
        "other_daily_shift": df.drop(index=[idx, idx+1] if idx+1 < len(df) else [idx]),
        "time_schedule": time_dic.get(location, pd.DataFrame())
    }
