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
    """① ファイル名から算出する日数と第一曜日 [source: 2]"""
    _, last_day = calendar.monthrange(y, m)
    w_list = ["月", "火", "水", "木", "金", "土", "日"]
    first_w = w_list[calendar.weekday(y, m, 1)]
    return last_day, first_w

def convert_to_time(val):
    """時程表用：6.50 => 08:30 等、15分刻みの変換 [source: 3]"""
    try:
        f_val = float(val)
        hours = int(f_val)
        minutes = int(round((f_val - hours) * 60))
        return f"{hours:02d}:{minutes:02d}"
    except:
        return val

def load_master_from_sheets(service, spreadsheet_id):
    """時程表読込方法：A列を検索し、勤務地ごとに辞書登録 [source: 3]"""
    spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    time_dic = {}
    for s in spreadsheet.get('sheets', []):
        title = s.get("properties", {}).get("title")
        res = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=f"'{title}'!A1:Z300").execute()
        vals = res.get('values', [])
        if not vals: continue
        df = pd.DataFrame(vals).fillna('')

        current_loc, start_idx = None, 0
        for i in range(len(df)):
            val_a = str(df.iloc[i, 0]).strip()
            if val_a != "":
                if current_loc:
                    time_dic[normalize(current_loc)] = process_time_block(df.iloc[start_idx:i, :])
                current_loc, start_idx = val_a, i
        if current_loc:
            time_dic[normalize(current_loc)] = process_time_block(df.iloc[start_idx:, :])
    return time_dic

def process_time_block(block):
    """勤務地行D列から時間列を抽出し変換 [source: 3]"""
    # 1行目(勤務地行)のD列(index 3)以降から数値列を検索
    time_cols = []
    for col in range(3, block.shape[1]):
        v = block.iloc[0, col]
        try:
            float(v); time_cols.append(col)
        except:
            if time_cols: break # 文字列が現れたら終了
    
    res_df = block.iloc[:, [0, 1, 2] + time_cols].copy()
    # 勤務地行のみ時間表記に変換 [source: 3]
    for i, col_idx in enumerate(time_cols):
        res_df.iloc[0, 3 + i] = convert_to_time(res_df.iloc[0, col_idx])
    # シフトコード行(1行目以降)はそのまま [source: 3]
    return res_df

def analyze_pdf_structure(pdf_path, y, m):
    """第一関門・座標設定・データ抽出 [source: 2]"""
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    if not tables: return None, "PDFから表を抽出できませんでした。"
    df = tables[0].df
    
    # ② ファイル内容から抽出 [source: 2]
    raw_0_0 = str(df.iloc[0, 0])
    dates = re.findall(r'\b([1-9]|[12][0-9]|3[01])\b', raw_0_0)
    days = re.findall(r'[月火水木金土日]', raw_0_0)
    pdf_last_day = int(max(dates)) if dates else 0
    pdf_first_w = days[0] if days else ""
    
    calc_last_day, calc_first_w = get_calc_date_info(y, m)
    
    # ①=②なら通過 [source: 2]
    if not (pdf_last_day == calc_last_day and pdf_first_w == calc_first_w):
        reason = f"不一致：計算={calc_last_day}日({calc_first_w}) / PDF={pdf_last_day}日({pdf_first_w})"
        return None, reason

    # <2> pdfファイル構造化 [source: 2]
    location = normalize(re.sub(r'[\d月火水木金土日\s]', '', raw_0_0))
    
    # データの組替
    staff_list = []
    rows = []
    rows.append([""] + df.iloc[0, 1:].tolist()) # 日付文字列
    rows.append([location] + df.iloc[1, 1:].tolist()) # location+曜日
    
    for i in range(2, len(df)):
        name = str(df.iloc[i, 0]).split('\n')[0].strip()
        rows.append([name] + df.iloc[i, 1:].tolist())
        if i % 2 == 0 and name and normalize(name) != location:
            staff_list.append(name)
            
    return {"df": pd.DataFrame(rows), "location": location, "staff_list": staff_list}, "通過"
