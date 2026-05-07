import pandas as pd
import camelot
import re
import calendar

def get_calc_date_info(y, m):
    """① ファイル名から算出する日数と第一曜日"""
    _, last_day = calendar.monthrange(y, m)
    w_list = ["月", "火", "水", "木", "金", "土", "日"]
    first_w = w_list[calendar.weekday(y, m, 1)]
    return last_day, first_w

def analyze_pdf_structure(pdf_path, y, m):
    """第1関門・第2関門の実行とlocationの精製"""
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    if not tables:
        return None, "PDFから表を抽出できませんでした。"
    
    df = tables[0].df
    raw_0_0 = str(df.iloc[0, 0]).replace('\n', ' ').strip()
    
    # --- 第1関門 ---
    calc_last_day, calc_first_w = get_calc_date_info(y, m)
    days_in_pdf = [int(n) for n in re.findall(r'\d+', raw_0_0)]
    pdf_last_day = max(days_in_pdf) if days_in_pdf else 0
    pdf_first_w_match = re.search(r'[月火水木金土日]', raw_0_0)
    pdf_first_w = pdf_first_w_match.group() if pdf_first_w_match else ""

    if pdf_last_day != calc_last_day or pdf_first_w != calc_first_w:
        return None, f"第1関門不通過: 算出={calc_last_day}{calc_first_w} / PDF={pdf_last_day}{pdf_first_w}"

    # --- 第2関門：[0,0]から曜日と日付を削除してlocationを抽出 ---
    # 1. 曜日文字列（月〜日）をすべて取得
    weekdays_found = re.findall(r'[月火水木金土日]', raw_0_0)
    num_weekdays = len(weekdays_found)
    
    # 2. 曜日を削除
    location = re.sub(r'[月火水木金土日]', '', raw_0_0)
    
    # 3. 曜日と同数の日付文字列（1〜31の独立した数字）を削除
    # \b を使い、年月の一部（2026の26など）ではない独立した数字をターゲットにする
    date_patterns = re.findall(r'\b(?:[1-9]|[12][0-9]|3[01])\b', location)
    # 曜日と同じ数だけ、日付数値を削除する
    for i in range(min(num_weekdays, len(date_patterns))):
        # 該当する数字を1回ずつ置換して消去
        location = re.sub(r'\b' + re.escape(date_patterns[i]) + r'\b', '', location, count=1)

    # 4. 残った定型句や記号、空白を掃除
    location = re.sub(r'\d{4}年\d{1,2}月度|勤務予定表|～|~|/|：|:', '', location)
    location = re.sub(r'\s+', '', location).strip()

    # スタッフ名リストの作成（第3関門用）
    staff_names = []
    for i in range(2, len(df), 2):
        name = str(df.iloc[i, 0]).split('\n')[0].strip()
        if name and name != location:
            staff_names.append(name)

    return {"df": df, "location": location, "staff_list": staff_names, "raw_0_0": raw_0_0}, "通過"
