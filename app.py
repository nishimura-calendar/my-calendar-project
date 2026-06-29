import camelot
import re
import calendar
from datetime import datetime

def check_first_gate(pdf_path, year, month):
    # --- A：理論上の最終日付と最終曜日 ---
    last_day = calendar.monthrange(year, month)[1]
    last_date_obj = datetime(year, month, last_day)
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    expected_weekday = weekdays_jp[last_date_obj.weekday()]

    # --- B：PDFファイルから最終日付と最終曜日を抽出 ---
    # 1. camelotを使用して読み込み
    tables = camelot.read_pdf(pdf_path, pages='all', flavor='stream')
    
    full_text = ""
    for table in tables:
        full_text += " ".join([" ".join(row) for row in table.df.values.astype(str)])
    
    # 2. 日付文字列(28-31)と曜日文字列を抽出
    all_dates = re.findall(r'\b(28|29|30|31)\b', full_text)
    all_weekdays = re.findall(r'[月火水木金土日]', full_text)
    
    # リストの最後を「最後の日付と曜日」として取得
    actual_last_date = int(all_dates[-1]) if all_dates else None
    actual_last_weekday = all_weekdays[-1] if all_weekdays else None

    # --- ⑤ A=Bなら通過、⑥ A≠Bなら停止 ---
    if actual_last_date == last_day and actual_last_weekday == expected_weekday:
        return True, actual_last_date, actual_last_weekday
    else:
        # ⑥ 不一致の場合は理由を表示して停止
        error_msg = f"不一致検知: 理論値 {last_day}({expected_weekday}) != 抽出値 {actual_last_date}({actual_last_weekday})"
        return False, error_msg

# 実行例
pdf_file = "免税店シフト表 1月度 第2ターミナル2026 (2).pdf"
is_match, result = check_first_gate(pdf_file, 2026, 2) # 2月度として判定

if is_match:
    print("第1関門通過：A=Bです。")
else:
    print(f"【プログラム停止】{result}")
    # 手順書に従い、ここでPDFを表示して終了する処理
