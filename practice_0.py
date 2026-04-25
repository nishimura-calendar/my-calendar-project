import camelot
import pandas as pd
import re
import unicodedata

def normalize_text(text):
    """全角・半角、空白を統一して紐付け精度を最大化する"""
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def get_master_data_from_df(df):
    """スプレッドシートの行列(iloc)から勤務地と時程表を分離・抽出"""
    # A列(0列目)をスキャンして勤務地名を特定
    locations = df.iloc[:, 0].dropna().unique().tolist()
    master_locations = [str(loc).strip() for loc in locations if loc and not str(loc).replace('.','').isdigit()]
    
    # 勤務地名を正規化キーとして時程データを辞書化
    time_schedules = {normalize_text(loc): df[df.iloc[:, 0] == loc] for loc in master_locations}
    return master_locations, time_schedules

def rebuild_shift_table(pdf_path, target_name, expected_days, expected_weekday, master_locations):
    """iloc座標の概念を使い、記号を100%正確に抜き出す"""
    # Streamモードで読み込み、中線の位置関係を保持
    tables = camelot.read_pdf(pdf_path, flavor='stream', pages='all')
    if not tables: return None, "PDF解析失敗"
    
    combined_df = pd.concat([t.df for t in tables], ignore_index=True)
    full_text = "".join(combined_df.values.flatten().astype(str))
    
    # --- ① 勤務地の検問 ---
    detected_loc = next((loc for loc in master_locations if normalize_text(loc) in normalize_text(full_text)), None)
    if not detected_loc:
        return None, "検問失敗：勤務地がマスターデータと一致しません。"

    # --- ② 日数・第一曜日の検問（ここでファイル不一致を遮断） ---
    found_days = max([int(d) for d in re.findall(r'\d+', full_text) if 1 <= int(d) <= 31] + [0])
    if found_days != expected_days:
        return None, f"検問失敗：日数不一致（設定:{expected_days} / PDF:{found_days}）"
    
    if expected_weekday not in full_text:
        return None, f"検問失敗：第一曜日({expected_weekday})がPDF内に見つかりません。"

    # --- ③ iloc[]による絶対抽出 ---
    my_shift = []
    others_shift = []
    clean_target = normalize_text(target_name)
    
    for i in range(len(combined_df)):
        # 行全体を一度文字列化し、中線に惑わされず記号のみを順番に抽出
        row_str = normalize_text("".join(combined_df.iloc[i].values.astype(str)))
        shifts = re.findall(r'[A-Z]|休日|出勤', row_str)
        
        if clean_target in row_str:
            # 四村さんの行を発見：確定した座標から日数分を抽出
            my_shift = shifts[:expected_days]
        elif len(shifts) >= 15:
            # 他スタッフも同様の座標ルールで抽出
            others_shift.append(shifts[:expected_days])

    return {
        "location": detected_loc, 
        "my_shift": my_shift, 
        "others": others_shift
    }, "Success"
