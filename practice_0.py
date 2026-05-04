import pandas as pd
import camelot
import re
import os
import calendar
import unicodedata
import streamlit as st

def normalize(text):
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', str(text)))

def get_calc_date_info(y, m):
    """① ファイル名から算出する日数と第一曜日"""
    _, last_day = calendar.monthrange(y, m)
    w_list = ["月", "火", "水", "木", "金", "土", "日"]
    first_w = w_list[calendar.weekday(y, m, 1)]
    return last_day, first_w

def convert_to_time(val):
    """時程表用：時間をHH:mm形式に変換[cite: 3]"""
    try:
        f_val = float(val)
        hours = int(f_val)
        minutes = int(round((f_val - hours) * 60))
        return f"{hours:02d}:{minutes:02d}"
    except:
        return val

def process_time_block(block):
    """時程表の構造化：勤務地行のD列以降を時間変換[cite: 3]"""
    time_cols = []
    for col in range(3, block.shape[1]):
        v = block.iloc[0, col]
        try:
            float(v); time_cols.append(col)
        except:
            if time_cols: break
    
    res_df = block.iloc[:, [0, 1, 2] + time_cols].copy()
    for i, col_idx in enumerate(time_cols):
        res_df.iloc[0, 3 + i] = convert_to_time(res_df.iloc[0, col_idx])
    return res_df

def analyze_pdf_structure(pdf_path, y, m):
    """第一関門：日数と第一曜日の照合"""
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    if not tables: return None, "PDFから表を抽出できませんでした。"
    df = tables[0].df
    
    # ② ファイル内容[0,0]から抽出
    raw_0_0 = str(df.iloc[0, 0])
    
    # 日付文字列から「1」から「31」までの数字をすべて抽出
    all_numbers = re.findall(r'\b([1-9]|[12][0-9]|3[01])\b', raw_0_0)
    pdf_dates = sorted([int(n) for n in all_numbers])
    # 末尾の数字を月末日とする
    pdf_last_day = pdf_dates[-1] if pdf_dates else 0
    # 最初の曜日文字を第一曜日とする
    days_found = re.findall(r'[月火水木金土日]', raw_0_0)
    pdf_first_w = days_found[0] if days_found else ""
    
    calc_last_day, calc_first_w = get_calc_date_info(y, m)
    
    # ①=②なら通過[cite: 4]
    if not (pdf_last_day == calc_last_day and pdf_first_w == calc_first_w):
        reason = f"理由: 計算上の月末は{calc_last_day}日({calc_first_w})ですが、PDFからは{pdf_last_day}日({pdf_first_w})が検出されました。"
        return None, reason

    # <2> pdfファイル構造化[cite: 4]
    location = normalize(re.sub(r'[\d月火水木金土日\s]', '', raw_0_0))
    
    rows = []
    rows.append([""] + df.iloc[0, 1:].tolist()) # 日付文字列
    rows.append([location] + df.iloc[1, 1:].tolist()) # location+曜日
    
    staff_list = []
    for i in range(2, len(df)):
        name = str(df.iloc[i, 0]).split('\n')[0].strip()
        rows.append([name] + df.iloc[i, 1:].tolist())
        if i % 2 == 0 and name: staff_list.append(name)
            
    return {"df": pd.DataFrame(rows), "location": location, "staff_list": staff_list}, "通過"
