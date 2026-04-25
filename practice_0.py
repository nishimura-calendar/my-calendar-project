import camelot
import pandas as pd
import re

def get_master_data(jiteihyo_df):
    """時程表から勤務地リストと、勤務地ごとのタイムスケジュールを抽出"""
    # A列から有効な勤務地を抽出
    locations = jiteihyo_df.iloc[:, 0].dropna().unique().tolist()
    master_locations = [str(loc).strip() for loc in locations if loc and not str(loc).replace('.','').isdigit()]
    
    # 勤務地ごとの詳細データ（Time Schedule）を保持
    time_schedules = {}
    for loc in master_locations:
        # A列がその勤務地の行から、次の勤務地が現れるまでの範囲を抽出
        loc_idx = jiteihyo_df[jiteihyo_df.iloc[:, 0] == loc].index[0]
        # 簡易的にその行周辺をスケジュールとして保持（B列=コード, D列以降=時間）
        time_schedules[loc] = jiteihyo_df.iloc[loc_idx:loc_idx+20].dropna(subset=[jiteihyo_df.columns[1]])
        
    return master_locations, time_schedules

def rebuild_shift_table(pdf_path, target_name, expected_days, expected_weekday, master_locations):
    # 1. PDF読み込み
    tables = camelot.read_pdf(pdf_path, flavor='stream', pages='all')
    if len(tables) == 0:
        return None, "PDFから表を抽出できませんでした。"
    
    combined_df = pd.concat([t.df for t in tables], ignore_index=True)
    full_text = "".join(combined_df.values.flatten().astype(str))
    
    # --- ① 勤務地の照合 ---
    detected_location = next((loc for loc in master_locations if loc in full_text), None)
    if not detected_location:
        return None, f"勤務地不一致: 時程表にある拠点名が見つかりません。({master_locations})"

    # --- ② 日数・第1曜日の確認 ---
    # 日数確認（PDF内の最大数値を抽出）
    found_days = max([int(d) for d in re.findall(r'\d+', full_text) if 1 <= int(d) <= 31] + [0])
    if found_days != expected_days:
        return None, f"日数不一致: PDFは{found_days}日ですが、設定は{expected_days}日です。"
    
    # 曜日確認（簡易判定）
    if expected_weekday not in full_text:
        return None, f"第1曜日不一致: PDF内に「{expected_weekday}曜日」の整合性が確認できません。"

    # --- データ抽出（my_shift / other_shift） ---
    my_shift = []
    others_shift = []
    
    for _, row in combined_df.iterrows():
        row_str = "".join(row.values.astype(str))
        shifts = re.findall(r'[A-Z]|休日|出勤', row_str)
        if target_name in row_str:
            my_shift = shifts[:expected_days]
        elif any(char in row_str for char in ["A", "B", "C"]): # 他スタッフらしき行
            others_shift.append({"raw": row_str, "shifts": shifts[:expected_days]})

    return {
        "location": detected_location,
        "my_shift": my_shift,
        "others_shift": others_shift,
        "raw_df": combined_df
    }, "Success"
