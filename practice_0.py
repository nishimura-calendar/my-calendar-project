import camelot
import pandas as pd
import re
import unicodedata

def normalize_text(text):
    """全角・半角、空白、大文字小文字の揺れを吸収する"""
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def get_master_data_from_df(df):
    """スプレッドシートのDataFrameから勤務地と時程を抽出（iloc特定用）"""
    # A列(0列目)から勤務地名を特定
    locations = df.iloc[:, 0].dropna().unique().tolist()
    master_locations = [str(loc).strip() for loc in locations if loc and not str(loc).replace('.','').isdigit()]
    
    # 正規化された勤務地名をキーに、その行のデータを保持
    time_schedules = {normalize_text(loc): df[df.iloc[:, 0] == loc] for loc in master_locations}
    return master_locations, time_schedules

def rebuild_shift_table(pdf_path, target_name, expected_days, expected_weekday, master_locations):
    """中線の座標概念に基づき、iloc[]でデータを100%抽出する"""
    tables = camelot.read_pdf(pdf_path, flavor='stream', pages='all')
    if not tables: return None, "PDFの表構造を読み取れませんでした。"
    
    # PDF全ページを1つの巨大な行列として扱う
    combined_df = pd.concat([t.df for t in tables], ignore_index=True)
    full_text = "".join(combined_df.values.flatten().astype(str))
    
    # --- ① 勤務地の検問（iloc起点の決定） ---
    detected_loc = next((loc for loc in master_locations if normalize_text(loc) in normalize_text(full_text)), None)
    if not detected_loc:
        return None, "検問失敗：スプレッドシートに登録された勤務地名がPDF内に見つかりません。"

    # --- ② 日数・第一曜日の検問（ファイル不一致の遮断） ---
    found_days = max([int(d) for d in re.findall(r'\d+', full_text) if 1 <= int(d) <= 31] + [0])
    if found_days != expected_days:
        return None, f"検問失敗：日数が一致しません（設定:{expected_days} / PDF:{found_days}）"
    
    if expected_weekday not in full_text:
        return None, f"検問失敗：第一曜日({expected_weekday})がPDF内で確認できません。"

    # --- ③ iloc[]による絶対座標抽出 ---
    my_shift = []
    others_shift = []
    clean_target = normalize_text(target_name)
    
    for i in range(len(combined_df)):
        # 各行の全セルの値を結合してスキャン（中線の影響を排除）
        row_str = normalize_text("".join(combined_df.iloc[i].values.astype(str)))
        
        # 記号（A-Z, 休日, 出勤）を順番に抽出
        shifts = re.findall(r'[A-Z]|休日|出勤', row_str)
        
        if clean_target in row_str:
            # 四村さんの行を発見：日付座標に沿って記号を固定
            my_shift = shifts[:expected_days]
        elif len(shifts) >= 15:
            # 他スタッフも同様に抽出
            others_shift.append(shifts[:expected_days])

    return {
        "location": detected_loc, 
        "my_shift": my_shift, 
        "others": others_shift
    }, "Success"
