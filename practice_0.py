import streamlit as st
import pandas as pd
import camelot
import re
import os
import calendar
import unicodedata

def normalize(text):
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', str(text)))

def get_date_info(y, m):
    # ① ファイル名・入力から算出した日数と第一曜日
    _, last_day = calendar.monthrange(y, m)
    w_list = ["月", "火", "水", "木", "金", "土", "日"]
    first_w = w_list[calendar.weekday(y, m, 1)]
    return last_day, first_w

def convert_to_time(val):
    # 時程表用：6.50 => 06:30 変換
    try:
        f_val = float(val)
        hours = int(f_val)
        minutes = int(round((f_val - hours) * 60))
        return f"{hours:02d}:{minutes:02d}"
    except:
        return val

def process_master_file(file):
    # 時程表読込ロジック
    df_master = pd.read_excel(file, header=None)
    time_dic = {}
    current_loc = None
    start_row = 0

    for i in range(len(df_master)):
        val_a = df_master.iloc[i, 0]
        if pd.notna(val_a) and str(val_a).strip() != "":
            if current_loc:
                time_dic[normalize(current_loc)] = extract_time_block(df_master.iloc[start_row:i, :])
            current_loc = str(val_a).strip()
            start_row = i
    if current_loc:
        time_dic[normalize(current_loc)] = extract_time_block(df_master.iloc[start_row:, :])
    return time_dic

def extract_time_block(block):
    # 勤務地行のD列(index 3)以降から数値列を抽出
    time_cols = []
    for col in range(3, block.shape[1]):
        v = block.iloc[0, col]
        try:
            float(v)
            time_cols.append(col)
        except:
            if time_cols: break
    
    res_df = block.iloc[:, [0, 1, 2] + time_cols].copy()
    # 勤務地行(0行目)のD列(3列目)以降のみ変換
    for c_idx in range(len(time_cols)):
        res_df.iloc[0, 3 + c_idx] = convert_to_time(res_df.iloc[0, 3 + c_idx])
    return res_df

def analyze_pdf(pdf_path, y, m):
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    if not tables: return None, "PDFから表を抽出できませんでした。"
    df = tables[0].df
    
    # [0,0]から情報抽出
    raw_0_0 = str(df.iloc[0, 0])
    dates_in_pdf = re.findall(r'\b([1-9]|[12][0-9]|3[01])\b', raw_0_0)
    days_in_pdf = re.findall(r'[月火水木金土日]', raw_0_0)
    
    pdf_last_day = int(max(dates_in_pdf)) if dates_in_pdf else 0
    pdf_first_w = days_in_pdf[0] if days_in_pdf else ""
    
    # 第一関門：①=②の判定
    calc_last_day, calc_first_w = get_date_info(y, m)
    if not (pdf_last_day == calc_last_day and pdf_first_w == calc_first_w):
        reason = f"不一致：計算上は{calc_last_day}日/{calc_first_w}曜日ですが、PDFは{pdf_last_day}日/{pdf_first_w}曜日です。"
        return None, reason

    # <1> 座標設定（概念的処理） & <2> location抽出
    location = re.sub(r'[\d月火水木金土日\s]', '', raw_0_0)
    
    # データの再構築
    final_rows = []
    # 0行目: 日付文字列
    final_rows.append([""] + df.iloc[0, 1:].tolist())
    # 1行目: location + 曜日文字列
    final_rows.append([location] + df.iloc[1, 1:].tolist())
    
    staff_list = []
    for i in range(2, len(df)):
        name = str(df.iloc[i, 0]).split('\n')[0].strip()
        final_rows.append([name] + df.iloc[i, 1:].tolist())
        if i % 2 == 0 and name: staff_list.append(name)
            
    return {"df": pd.DataFrame(final_rows), "location": normalize(location), "staff_list": staff_list}, "通過"
