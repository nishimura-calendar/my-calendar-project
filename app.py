import re
import camelot

def extract_last_date_and_day(pdf_path, target_key="T1"):
    # (1) Camelotを使用して読込
    tables = camelot.read_pdf(pdf_path, flavor='lattice', pages='all')
    
    full_text = ""
    for table in tables:
        full_text += table.df.to_string()
        
    # (2) 第1関門: Key検索
    # 手順書に基づき、Keyの出現位置を特定
    key_match = re.search(rf"\b{re.escape(target_key)}\b", full_text)
    
    if not key_match:
        return None, None, "Keyが見当たりません。"
    
    # Key以降の領域に探索範囲を限定
    header_area = full_text[key_match.end():]
    
    # (3) 第2関門: 最終日付と曜日の抽出
    # 領域内のすべての日付と曜日をリスト化
    all_dates = re.findall(r'\b([1-9]|[12][0-9]|3[01])\b', header_area)
    all_days = re.findall(r'[日月火水木金土]', header_area)
    
    if not all_dates or not all_days:
        return None, None, "日付・曜日のペアが見つかりませんでした。"
        
    # リストの最後尾が「その表の最終日」になるはず
    last_date = all_dates[-1]
    last_day = all_days[-1]
    
    return last_date, last_day, None

# 実行例
pdf_file = "免税店シフト表 1月度 第1ターミナル 2026.pdf"
last_date, last_day, error = extract_last_date_and_day(pdf_file)

if error:
    print(error)
else:
    print(f"最終日付: {last_date}日")
    print(f"最終曜日: {last_day}曜日")
