import camelot
import pandas as pd
import re

def get_master_data(sh):
    """Googleスプレッドシートから勤務地リストと時程表を取得"""
    worksheet = sh.get_worksheet(0)
    data = worksheet.get_all_values()
    df = pd.DataFrame(data[1:], columns=data[0])
    
    # A列から有効な勤務地（T1, T2等）を抽出
    locations = df.iloc[:, 0].dropna().unique().tolist()
    master_locations = [str(loc).strip() for loc in locations if loc and not str(loc).replace('.','').isdigit()]
    
    # 勤務地ごとの時間定義を辞書化
    time_schedules = {loc: df[df.iloc[:, 0] == loc] for loc in master_locations}
    return master_locations, time_schedules

def rebuild_shift_table(pdf_path, target_name, expected_days, expected_weekday, master_locations):
    # Streamモードで読み込み
    tables = camelot.read_pdf(pdf_path, flavor='stream', pages='all')
    if not tables: return None, "PDF読み取り失敗"
    
    combined_df = pd.concat([t.df for t in tables], ignore_index=True)
    full_text = "".join(combined_df.values.flatten().astype(str))
    
    # --- ① 勤務地の検問 ---
    detected_loc = next((loc for loc in master_locations if loc in full_text), None)
    if not detected_loc:
        return None, f"勤務地不一致: PDF内にマスターの勤務地が見つかりません。"

    # --- ② 日数・第一曜日の検問 ---
    found_days = max([int(d) for d in re.findall(r'\d+', full_text) if 1 <= int(d) <= 31] + [0])
    if found_days != expected_days:
        return None, f"日数不一致: 設定{expected_days}日に対し、PDFは{found_days}日です。"
    
    if expected_weekday not in full_text:
        return None, f"第一曜日不一致: PDF内に「{expected_weekday}曜日」が確認できません。"

    # --- ③ データの抽出・座標固定 ---
    my_shift = []
    others_shift = []
    for _, row in combined_df.iterrows():
        row_str = "".join(row.values.astype(str))
        # 記号を座標として抽出
        shifts = re.findall(r'[A-Z]|休日|出勤', row_str) 
        if target_name in row_str:
            my_shift = shifts[:expected_days]
        elif len(shifts) >= expected_days // 2:
            others_shift.append(shifts[:expected_days])

    return {"location": detected_loc, "my_shift": my_shift, "others": others_shift}, "Success"
