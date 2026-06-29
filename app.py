import camelot
import re
import calendar
from datetime import datetime

def check_pdf_first_gate(pdf_path):
    # --- [2] <1> (2) ① 年月の取得 ---
    # ファイル名から "2026年1月" のようなパターンを抽出する例
    match = re.search(r'(\d{4}).*?(\d{1,2})', pdf_path)
    if match:
        year, month = int(match.group(1)), int(match.group(2))
    else:
        # 取得できない場合は②へ (ここでは簡単のためエラー停止)
        print("ファイル名から年月を取得できませんでした。ユーザー入力を促してください。")
        return False

    # --- ③ A：理論上の最終日付と最終曜日 ---
    last_day = calendar.monthrange(year, month)[1]
    last_date_obj = datetime(year, month, last_day)
    # 曜日インデックス: 0=月, 1=火, ... 5=土, 6=日
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    expected_weekday = weekdays_jp[last_date_obj.weekday()]

    # --- ④ B：PDFから最終情報を抽出 ---
    # (1) camelotを使用して読込
    tables = camelot.read_pdf(pdf_path, pages='all', flavor='stream')
    
    full_text = ""
    for table in tables:
        full_text += " ".join([" ".join(row) for row in table.df.values.astype(str)])
    
    # 1. 曜日・日付の抽出
    all_dates = re.findall(r'\b(28|29|30|31)\b', full_text)
    all_weekdays = re.findall(r'[月火水木金土日]', full_text)
    
    # リストの末尾が最も後の情報
    actual_last_date = int(all_dates[-1]) if all_dates else None
    actual_last_weekday = all_weekdays[-1] if all_weekdays else None

    # --- ⑤ A=Bなら通過、⑥ A≠Bなら停止 ---
    if actual_last_date == last_day and actual_last_weekday == expected_weekday:
        print(f"第1関門通過: {actual_last_date}日({actual_last_weekday})")
        return True
    else:
        # ⑥ A≠Bなら理由を表示してプログラム停止
        print("【プログラム停止】")
        print(f"理由: 理論上の最終日 {last_day}({expected_weekday}) とPDF抽出値 {actual_last_date}({actual_last_weekday}) が一致しません。")
        # ここでpdfシフト表を表示する処理を想定
        return False

# --- 実行 ---
if __name__ == "__main__":
    pdf_file = "免税店シフト表 1月度 第1ターミナル 2026.pdf"
    check_pdf_first_gate(pdf_file)
