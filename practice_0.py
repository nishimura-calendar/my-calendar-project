import pandas as pd
import camelot
import re
import unicodedata
import streamlit as st

def normalize_text(text):
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def extract_year_month_from_text(text):
    text = unicodedata.normalize('NFKC', text)
    y_match = re.search(r'(\d{4})年', text)
    m_match = re.search(r'\((\d{1,2})\)', text) # "26(1)"形式
    if not m_match:
        m_match = re.search(r'(\d{1,2})月', text)
    
    y_val = int(y_match.group(1)) if y_match else 2026
    m_val = int(m_match.group(1)) if m_match else None
    return y_val, m_val

def pdf_reader_engine(uploaded_pdf, l_boundary):
    with open("temp.pdf", "wb") as f:
        f.write(uploaded_pdf.getbuffer())
    
    tables = camelot.read_pdf(
        "temp.pdf", pages='1', flavor='stream',
        columns=[str(l_boundary)], 
        row_tol=10, # あえて広めに取り、合体した行を確実に捕まえる
        strip_text='\n'
    )
    
    if not tables: return None
    df = tables[0].df

    # --- セルの再構築ロジック ---
    # もし0行1列目に数字が固まっている場合、それを列に展開する
    raw_dates = str(df.iloc[0, 1])
    if "12345" in raw_dates:
        # 数字を一つずつ切り出す(1-9は1文字、10-31は2文字として処理)
        # 実際には Camelot の columns 指定により、既に列が分かれているべきですが
        # 合体している場合は、正規表現で数字のリストを抽出します
        extracted_days = re.findall(r'\d+', raw_dates)
        
        # タイトル由来の「2026」や「1」を除去し、1〜31の並びだけを残す
        clean_days = [d for d in extracted_days if 1 <= int(d) <= 31]
        
        # 新しい行データを作成 ([0,0]は空、[0,1]から日付)
        new_row = [""] * df.shape[1]
        for i, d in enumerate(clean_days):
            if i + 1 < len(new_row):
                new_row[i + 1] = d
        df.iloc[0] = new_row

    return df

def get_actual_info(df, sheet_id):
    # 0行目にある最大の数字を末日とする
    days = []
    for val in df.iloc[0, 1:]:
        d = re.findall(r'\d+', str(val))
        if d: days.append(int(d[0]))
    
    actual_last_day = max(days) if days else 0
    
    # 勤務地の特定 (0列目検索)
    col0_text = "".join(df.iloc[:, 0].astype(str))
    detected_loc = "T2" if "T2" in col0_text else "不明"
    
    return actual_last_day, detected_loc
