import streamlit as st
import camelot
import re
import calendar
import tempfile
from datetime import datetime

def check_first_gate(pdf_path, year, month):
    # A：理論値算出
    last_day = calendar.monthrange(year, month)[1]
    last_date_obj = datetime(year, month, last_day)
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    expected_weekday = weekdays_jp[last_date_obj.weekday()]

    # B：PDFから抽出（ペア検索による堅牢なロジック）
    tables = camelot.read_pdf(pdf_path, pages='all', flavor='stream')
    # セルの中身をすべて連結して一つのテキストにする
    full_text = " ".join([str(cell).replace('\n', ' ') for table in tables for row in table.df.values for cell in row])
    
    # 【改良】日付(28-31)の直後（0〜4文字以内）に曜日があるものを探す
    # .{0,4}? は、日付と曜日の間にスペースや改行が数文字あっても許容する意味です
    matches = re.finditer(r'(28|29|30|31).{0,10}?([月火水木金土日])', full_text)
    
    candidates = []
    for m in matches:
        # 日付と曜日をペアでリストに追加
        candidates.append((int(m.group(1)), m.group(2)))
    
    if not candidates:
        return False, None, None
        
    # 日付が最大のものを「末尾のデータ」として確定する
    actual_last_date, actual_last_weekday = max(candidates, key=lambda x: x[0])

    # 判定
    if actual_last_date == last_day and actual_last_weekday == expected_weekday:
        return True, actual_last_date, actual_last_weekday
    else:
        return False, actual_last_date, actual_last_weekday
