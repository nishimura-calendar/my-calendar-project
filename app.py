import re

def extract_final_date_day(full_text):
    # 1. T1の出現位置を探す（ここからがヘッダー領域）
    t1_match = re.search(r'T1', full_text)
    if not t1_match:
        return None, None
    
    # T1以降のテキストを切り出し
    header_area = full_text[t1_match.end():]
    
    # 2. その領域内にある日付と曜日を全て抽出
    dates = re.findall(r'\b([1-9]|[12][0-9]|3[01])\b', header_area)
    days = re.findall(r'[日月火水木金土]', header_area)
    
    # 3. 最終日付と最終曜日のペアを取得
    # ヘッダー領域であれば、リストの最後が月末の31日になるはずです
    if dates and days:
        return dates[-1], days[-1]
    return None, None

# 実行
final_date, final_day = extract_final_date_day(full_text)
print(f"最終日付: {final_date}日")
print(f"最終曜日: {final_day}曜日")
