import pandas as pd
import camelot
import re
import unicodedata
import streamlit as st

def normalize_text(text):
    if not isinstance(text, str): return ""
    # 全角半角の正規化と空白削除
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def extract_year_month_from_text(text):
    """ファイル名から年月を抽出する"""
    text = unicodedata.normalize('NFKC', text)
    # 「2026年1月」や「26(1)」などの形式に対応
    y_match = re.search(r'(\d{4})年', text)
    m_match = re.search(r'(\d{1,2})月', text)
    
    # 万が一「26(1)」のような形式の場合の予備ロジック
    if not m_match:
        m_match = re.search(r'\((\d{1,2})\)', text)
    
    y_val = int(y_match.group(1)) if y_match else 2026
    m_val = int(m_match.group(1)) if m_match else None
    return y_val, m_val

def pdf_reader_engine(uploaded_pdf, l_boundary):
    """PDFをDataFrameに変換する"""
    with open("temp.pdf", "wb") as f:
        f.write(uploaded_pdf.getbuffer())
    
    # row_tol=3 に設定して、タイトル・日付・曜日の分離を安定させる
    tables = camelot.read_pdf(
        "temp.pdf", pages='1', flavor='stream',
        columns=[str(l_boundary)], 
        row_tol=3, 
        strip_text='\n'
    )
    return tables[0].df if tables else None

def get_actual_info(df, sheet_id):
    """PDFの0列目と0行目から情報を検索する"""
    # 1. 末日の特定 (0行目の中で一番大きい数字)
    row0_str = "".join(df.iloc[0, :].astype(str))
    days = re.findall(r'\d+', row0_str)
    # 「2026」などの年を除外するため、31以下の最大値を探す
    day_list = [int(d) for d in days if int(d) <= 31]
    actual_last_day = max(day_list) if day_list else 0
    
    # 2. 勤務地の特定 (0列目に時程表のキーワードがあるか)
    # 今回は「T2」を優先的に探し、なければ「免税店」などを探す
    detected_loc = "不明"
    col0_text = "".join(df.iloc[:, 0].astype(str))
    
    if "T2" in col0_text:
        detected_loc = "T2"
    elif "免税" in col0_text:
        detected_loc = "免税店"
    
    return actual_last_day, detected_loc

def rebuild_shift_data(df, sheet_id, target_staff, location):
    """時程表とPDFデータを統合する"""
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    try:
        time_master = pd.read_csv(url)
    except:
        return None

    clean_target = normalize_text(target_staff)
    # 0列目を正規化して氏名を検索
    search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
    
    indices = df.index[search_col == clean_target].tolist()
    if not indices:
        return None
    
    target_idx = indices[0]
    # 本人シフト（2行分、0列目以外のデータ）
    my_shift = df.iloc[target_idx:target_idx+2, 1:].copy()
    
    return {
        "my_shift": my_shift,
        "time_master": time_master
    }
