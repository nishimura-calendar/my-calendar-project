import streamlit as st
import pandas as pd
import re
import unicodedata
import camelot
import os

# --- ユーティリティ・変換関数 ---
def normalize_text(text):
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def convert_num_to_time_str(val):
    """数値(6.25等)を時刻(06:15)に変換。文字列はそのまま。"""
    try:
        # 数値（int/float）または数値形式の文字列のみ変換
        num = float(val)
        hours = int(num)
        minutes = int(round((num - hours) * 60))
        return f"{hours:02d}:{minutes:02d}"
    except (ValueError, TypeError):
        return str(val)

# --- スプレッドシート抽出ロジック ---
def time_schedule_from_drive(sheets_service, file_id):
    spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=file_id).execute()
    sheets = spreadsheet.get('sheets', [])
    location_data_dic = {}

    for s in sheets:
        title = s.get("properties", {}).get("title")
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=file_id, range=f"'{title}'!A1:Z300").execute()
        vals = result.get('values', [])
        if not vals: continue

        df = pd.DataFrame(vals).fillna('')
        current_key, start_row = None, 0
        
        for i in range(len(df)):
            val_a = str(df.iloc[i, 0]).strip()
            if val_a != "":
                if current_key is not None:
                    # 前の拠点の範囲を確定
                    location_data_dic[normalize_text(current_key)] = extract_with_string_b_col(df.iloc[start_row:i, :])
                current_key, start_row = val_a, i
        
        if current_key is not None:
            location_data_dic[normalize_text(current_key)] = extract_with_string_b_col(df.iloc[start_row:, :])
                
    return location_data_dic

def extract_with_string_b_col(loc_df):
    """
    幅方向: A-C列 + 時間列。
    B列(シフトコード)は文字列を維持。
    時間列は『勤務地行』のD列以降で数値がヒットした範囲のみ。
    """
    key_row = loc_df.iloc[0, :].tolist()
    col_start, col_end = None, len(key_row)

    # 1. 勤務地行のD列(3)以降で、最初に数値がヒットする列を探す
    for c in range(3, len(key_row)):
        if re.match(r'^\d+(\.\d+)?$', str(key_row[c]).strip()):
            col_start = c
            break

    if col_start is None:
        return loc_df.iloc[:, 0:3]

    # 2. 数値が途切れ、文字列が現れるまでを特定
    for c in range(col_start, len(key_row)):
        val_str = str(key_row[c]).strip()
        if val_str != "" and not re.match(r'^\d+(\.\d+)?$', val_str):
            col_end = c
            break

    # 3. 分割抽出
    base_info = loc_df.iloc[:, 0:3].copy() # A, B, C列
    time_data = loc_df.iloc[:, col_start:col_end].copy() # 時間数値列

    # 4. 時間列のみに変換を適用。B列(base_infoの1列目)は触らない。[cite: 8]
    for col in time_data.columns:
        time_data[col] = time_data[col].apply(convert_num_to_time_str)
            
    return pd.concat([base_info, time_data], axis=1)

# --- PDF解析 (0列目検索) ---
def get_key_and_schedule(pdf_stream, time_dic):
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
    try:
        tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice')
        if not tables: return None
        
        df = tables[0].df
        matched_key = None
        raw_val = None

        # PDFの0列目全体を検索して、マスターのKeyと一致する行を探す[cite: 7, 8]
        for val in df.iloc[:, 0]:
            clean_val = normalize_text(re.sub(r'[\d/:()月火水木金土日]', '', str(val)))
            if not clean_val: continue
            
            # 部分一致で検索
            found_key = next((k for k in time_dic.keys() if clean_val in k or k in clean_val), None)
            if found_key:
                matched_key = found_key
                raw_val = val
                break
        
        if matched_key:
            return {'key': matched_key, 'time_schedule': time_dic[matched_key], 'raw': raw_val}
    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")
    return None
