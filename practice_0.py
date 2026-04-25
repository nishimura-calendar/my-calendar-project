import camelot
import pandas as pd
import re

def get_master_data_from_gsheets(sh):
    """Googleスプレッドシートから勤務地と時程表を取得"""
    # 最初のシートを読み込む例
    worksheet = sh.get_worksheet(0)
    df = pd.DataFrame(worksheet.get_all_records())
    
    # A列から有効な勤務地を抽出
    locations = df.iloc[:, 0].dropna().unique().tolist()
    master_locations = [str(loc).strip() for loc in locations if loc and not str(loc).replace('.','').isdigit()]
    
    time_schedules = {}
    for loc in master_locations:
        # 勤務地ごとの時間データを保持（B列=コード、D列以降=時間）
        time_schedules[loc] = df[df.iloc[:, 0] == loc] # 簡易的なフィルタリング
        
    return master_locations, time_schedules

def rebuild_shift_table(pdf_path, target_name, expected_days, expected_weekday, master_locations):
    # Streamモードで読み込み
    tables = camelot.read_pdf(pdf_path, flavor='stream', pages='all')
    if len(tables) == 0:
        return None, "PDFから表を抽出できませんでした。"
    
    combined_df = pd.concat([t.df for t in tables], ignore_index=True)
    full_text = "".join(combined_df.values.flatten().astype(str))
    
    # --- ① 勤務地の照合 ---
    detected_location = next((loc for loc in master_locations if loc in full_text), None)
    if not detected_location:
        return None, f"勤務地不一致: 時程表にある拠点名が見つかりません。対象: {master_locations}"

    # --- ② 日数・第1曜日の確認 ---
    found_days = max([int(d) for d in re.findall(r'\d+', full_text) if 1 <= int(d) <= 31] + [0])
    if found_days != expected_days:
        return None, f"日数不一致: 設定は{expected_days}日ですが、PDFは{found_days}日です。"
    
    if expected_weekday not in full_text:
        return None, f"第1曜日不一致: PDF内に「{expected_weekday}曜日」が確認できません。"

    # --- データ抽出 ---
    my_shift = []
    others_shift = []
    
    for _, row in combined_df.iterrows():
        row_str = "".join(row.values.astype(str))
        # 英字1文字、または「休日」「出勤」を抽出
        shifts = re.findall(r'[A-Z]|休日|出勤', row_str)
        if target_name in row_str:
            my_shift = shifts[:expected_days]
        elif len(shifts) >= expected_days // 2: # 一定以上の記号がある行を他スタッフとみなす
            others_shift.append(shifts[:expected_days])

    return {
        "location": detected_location,
        "my_shift": my_shift,
        "others_shift": others_shift,
        "raw_df": combined_df
    }, "Success"
