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
    """時程表の数値(6.5など)を時刻(06:30)に変換"""
    try:
        f_val = float(val)
        hours = int(f_val)
        minutes = int(round((f_val - hours) * 60))
        return f"{hours:02d}:{minutes:02d}"
    except:
        return val

def load_master_from_sheets(service, spreadsheet_id):
    """時程表を読み込み、勤務地ごとに辞書登録する"""
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
    """時程表の構造化：勤務地行のみ時間を変換し、他は維持[cite: 3]"""
    time_cols = []
    # 勤務地行のD列(index 3)以降から数値列を特定
    for col in range(3, block.shape[1]):
        v = block.iloc[0, col]
        try:
            float(v)
            time_cols.append(col)
        except:
            if time_cols: break
    
    res_df = block.iloc[:, [0, 1, 2] + time_cols].copy()
    # 勤務地行(0行目)のD列以降のみ変換
    for i, _ in enumerate(time_cols):
        res_df.iloc[0, 3 + i] = convert_to_time(res_df.iloc[0, 3 + i])
    return res_df

def analyze_pdf_structure(pdf_path, y, m):
    """第一関門・座標設定・PDF抽出[cite: 4]"""
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    if not tables: return None, "PDFから表を抽出できませんでした。"
    df = tables[0].df
    
    raw_0_0 = str(df.iloc[0, 0])
    # 日付・曜日の抽出
    all_numbers = re.findall(r'\b([1-9]|[12][0-9]|3[01])\b', raw_0_0)
    pdf_dates = sorted([int(n) for n in all_numbers])
    pdf_last_day = pdf_dates[-1] if pdf_dates else 0
    days_found = re.findall(r'[月火水木金土日]', raw_0_0)
    pdf_first_w = days_found[0] if days_found else ""
    
    calc_last_day, calc_first_w = get_calc_date_info(y, m)
    
    # 第一関門判定[cite: 4]
    if not (pdf_last_day == calc_last_day and pdf_first_w == calc_first_w):
        reason = f"不一致：計算={calc_last_day}日({calc_first_w}) / PDF={pdf_last_day}日({pdf_first_w})"
        return None, reason

    # location抽出[cite: 4]
    location = normalize(re.sub(r'[\d月火水木金土日\s]', '', raw_0_0))
    
    # PDFデータの組替[cite: 4]
    rows = []
    rows.append([""] + df.iloc[0, 1:].tolist()) # 0行目: 日付
    rows.append([location] + df.iloc[1, 1:].tolist()) # 1行目: location+曜日
    
    staff_list = []
    for i in range(2, len(df)):
        name = str(df.iloc[i, 0]).split('\n')[0].strip()
        rows.append([name] + df.iloc[i, 1:].tolist())
        if i % 2 == 0 and name: staff_list.append(name)
            
    return {"df": pd.DataFrame(rows), "location": location, "staff_list": staff_list}, "通過"
