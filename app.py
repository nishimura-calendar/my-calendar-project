import camelot
import re
import calendar

def get_last_date_info_direct(pdf_path, year, month):
    """
    手順[2] <1> (1) camelotを使用して読込
    手順[2] <1> (2) 個数判定を使わず、PDF内の末尾情報を直接取得
    """
    # A：年月から理論上の最終日を取得
    last_day = calendar.monthrange(year, month)[1]
    last_date_obj = calendar.date(year, month, last_day)
    expected_weekday = ["月", "火", "水", "木", "金", "土", "日"][last_date_obj.weekday()]

    # B：PDFファイルから末尾情報を直接取得
    tables = camelot.read_pdf(pdf_path, pages='all', flavor='stream')
    
    # 全テーブルのテキストを結合して末尾を探す
    full_text = ""
    for table in tables:
        # テーブル内の全セルを結合
        full_text += " ".join([" ".join(row) for row in table.df.values.astype(str)])
    
    # 末尾付近の日付（28~31）と曜日を正規表現で全抽出
    all_dates = re.findall(r'\b(28|29|30|31)\b', full_text)
    all_weekdays = re.findall(r'[月火水木金土日]', full_text)
    
    # リストの最後にある要素が、PDF上の最も後の情報であるとみなす
    actual_last_date = int(all_dates[-1]) if all_dates else None
    actual_last_weekday = all_weekdays[-1] if all_weekdays else None
    
    # 照合（⑤ A=Bなら通過、⑥ A≠Bなら停止）
    if actual_last_date == last_day and actual_last_weekday == expected_weekday:
        return True, actual_last_date, actual_last_weekday
    else:
        # ⑥ A≠Bの場合はここで理由を表示して停止
        print(f"【第1関門エラー】不一致検知: 理論値 {last_day}({expected_weekday}) != 抽出値 {actual_last_date}({actual_last_weekday})")
        return False, actual_last_date, actual_last_weekday

# 実行例
# success, d, w = get_last_date_info_direct("免税店シフト表 1月度 第1ターミナル 2026.pdf", 2026, 1)
