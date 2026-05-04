import streamlit as st
import pandas as pd
import re
import unicodedata
import camelot
import os
import math
import calendar
from googleapiclient.discovery import build
from google.oauth2 import service_account

# ... (認証・正規化・時程表読込関数は変更なし) ...

def verify_first_gate(filename, pdf_0_0, manual_date=None):
    if manual_date:
        y, m = manual_date
    else:
        # ご提案のロジック:
        # 年: ファイル名全体から4桁の数字を検索
        match_y = re.search(r'(\d{4})', filename)
        # 月: ファイル名の先頭から検索して最初に見つかる1〜2桁の数字
        match_m = re.search(r'(\d{1,2})', filename)
        
        if match_y and match_m:
            y = int(match_y.group(1))
            m = int(match_m.group(1))
        else:
            return False, "ファイル名から年月を特定できません", None
    
    # 整合性チェック (source: 9)
    _, last_day_calc = calendar.monthrange(y, m)
    w_list = ["月", "火", "水", "木", "金", "土", "日"]
    first_w_calc = w_list[calendar.weekday(y, m, 1)]

    found_dates = [int(d) for d in re.findall(r'\b([1-9]|[12][0-9]|3[01])\b', pdf_0_0)]
    found_days = re.findall(r'[月火水木金土日]', pdf_0_0)
    
    last_day_pdf = max(found_dates) if found_dates else 0
    first_w_pdf = found_days[0] if found_days else ""

    if last_day_calc == last_day_pdf and first_w_calc == first_w_pdf:
        return True, "通過", (found_dates, found_days, y, m)
    return False, f"整合性エラー: 算出={last_day_calc}日({first_w_calc}) / PDF={last_day_pdf}日({first_w_pdf})", None

# analyze_pdf_structural 等は変更なし
