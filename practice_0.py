import camelot
import pandas as pd
import re
import unicodedata

def normalize_text(text):
    """全角・半角、空白を統一して比較精度を高める"""
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def get_master_data(sh):
    """スプレッドシートから勤務地と時程表を取得（iloc特定用）"""
    worksheet = sh.get_worksheet(0)
    data = worksheet.get_all_values()
    df = pd.DataFrame(data[1:], columns=data[0])
    
    # A列から勤務地名をリスト化
    locations = df.iloc[:, 0].dropna().unique().tolist()
    master_locations = [str(loc).strip() for loc in locations if loc and not str(loc).replace('.','').isdigit()]
    
    # 勤務地ごとの時間定義を辞書化（正規化キー）
    time_schedules = {normalize_text(loc): df[df.iloc[:, 0] == loc] for loc in master_locations}
    return master_locations, time_schedules

def rebuild_shift_table(pdf_path, target_name, expected_days, expected_weekday, master_locations):
    """iloc[]の概念に基づき、座標を特定して抽出する"""
    tables = camelot.read_pdf(pdf_path, flavor='stream', pages='all')
    if not tables: return None, "PDF解析失敗"
    
    # 全ページを結合して巨大な行列（ilocの対象）を作成
    combined_df = pd.concat([t.df for t in tables], ignore_index=True)
    full_text = "".join(combined_df.values.flatten().astype(str))
    
    # --- ① 勤務地の検問 ---
    detected_loc = next((loc for loc in master_locations if normalize_text(loc) in normalize_text(full_text)), None)
    if not detected_loc:
        return None, f"検問失敗：勤務地が一致しません（マスター：{master_locations}）"

    # --- ② 日数・第一曜日の絶対座標検問 ---
    found_days = max([int(d) for d in re.findall(r'\d+', full_text) if 1 <= int(d) <= 31] + [0])
    if found_days != expected_days:
        return None, f"検問失敗：日数不一致（設定：{expected_days}日 / PDF：{found_days}日）"
    
    if expected_weekday not in full_text:
        return None, f"検問失敗：第一曜日不一致（PDF内に {expected_weekday}曜日 がありません）"

    # --- ③ iloc[]によるデータ抽出 ---
    my_shift = []
    others_shift = []
    clean_target = normalize_text(target_name)
    
    for i in range(len(combined_df)):
        # 行（row）を文字列として結合
        row_str = normalize_text("".join(combined_df.iloc[i].values.astype(str)))
        
        # 中線の座標に基づいた列から記号を抽出
        shifts = re.findall(r'[A-Z]|休日|出勤', row_str)
        
        if clean_target in row_str:
            # ターゲット（四村さん）の行を発見した場合、日数分の座標を確定
            my_shift = shifts[:expected_days]
        elif len(shifts) >= 15:
            # 他スタッフも同様に抽出
            others_shift.append(shifts[:expected_days])

    return {
        "location": detected_loc, 
        "my_shift": my_shift, 
        "others": others_shift
    }, "Success"
