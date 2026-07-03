import streamlit as st
import camelot
import re
import calendar
import tempfile
from datetime import datetime

def check_first_gate(pdf_path, year, month):
    """
    第1関門：理論値とPDF抽出値の照合
    """
    # A：理論値算出（その月の最終日と曜日を取得）
    last_day = calendar.monthrange(year, month)[1]
    last_date_obj = datetime(year, month, last_day)
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    expected_weekday = weekdays_jp[last_date_obj.weekday()]

    # B：PDFから最終日付と曜日を抽出
    # Camelotで読み込み、全セルを結合して平坦な文字列にする
    try:
        tables = camelot.read_pdf(pdf_path, pages='all', flavor='stream')
        full_text = " ".join([str(cell).replace('\n', ' ') for table in tables for row in table.df.values for cell in row])
    except Exception as e:
        st.error(f"PDF読み込みエラー: {e}")
        return False, None, None

    # 日付(28-31)の直後（0〜4文字の間）に曜日があるペアを全て抽出
    # このロジックにより、ヘッダーの年号や不規則な配置を無視して月末を特定可能
    matches = re.finditer(r'(28|29|30|31).{0,4}?([月火水木金土日])', full_text)
    
    candidates = []
    for m in matches:
        candidates.append((int(m.group(1)), m.group(2)))
    
    if not candidates:
        return False, None, None
        
    # 候補の中から日付が最大のものを「末尾のデータ」として採用
    actual_last_date, actual_last_weekday = max(candidates, key=lambda x: x[0])

    # ⑤ 判定（理論値と抽出値の照合）
    if actual_last_date == last_day and actual_last_weekday == expected_weekday:
        return True, actual_last_date, actual_last_weekday
    else:
        return False, actual_last_date, actual_last_weekday

# --- UI実装のイメージ（Streamlit） ---
# 必要に応じて、ファイルアップロード後の処理フローに組み込んでください
