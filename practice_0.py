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
    m_match = re.search(r'(\d{1,2})月', text)
    y_match = re.search(r'(\d{4})年', text)
    y_val = int(y_match.group(1)) if y_match else 2026
    m_val = int(m_match.group(1)) if m_match else None
    return y_val, m_val

def pdf_reader_engine(uploaded_pdf, l_boundary):
    with open("temp.pdf", "wb") as f:
        f.write(uploaded_pdf.getbuffer())
    # 座標lで分断し、row_tol=2で高さ2pt単位で分離(日付・勤務地の分離)
    tables = camelot.read_pdf(
        "temp.pdf", pages='1', flavor='stream',
        columns=[str(l_boundary)], 
        row_tol=2, 
        strip_text='\n'
    )
    return tables[0].df if tables else None

def time_schedule_from_drive(sheet_id):
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv"
    try:
        df = pd.read_csv(url)
        # 時程表のマスターとしてT2等をキーに辞書化(運用に応じ拡張)
        return {"T2": df} 
    except Exception as e:
        st.error(f"時程表の取得に失敗しました: {e}")
        return {}

def data_integration_v2(df_pdf, time_schedule_dic, target_staff, detected_loc):
    integrated_dic = {}
    clean_target = normalize_text(target_staff)
    
    # 時程表マスターを基準に処理
    for loc_key in time_schedule_dic.keys():
        # PDFから抽出した勤務地(detected_loc)がマスター名を含んでいるか
        if loc_key in detected_loc:
            search_col = df_pdf.iloc[:, 0].astype(str).apply(normalize_text)
            matched = df_pdf.index[search_col == clean_target].tolist()
            
            if matched:
                idx = matched[0]
                # 本人分(2行)と他スタッフ(ヘッダー[0,1]と本人以外)
                my_shift = df_pdf.iloc[idx : idx+2, :].copy()
                other_shift = df_pdf.drop([0, 1, idx, idx+1], errors='ignore').copy()
                
                integrated_dic[loc_key] = {
                    "time_schedule": time_schedule_dic[loc_key],
                    "my_daily_shift": my_shift,
                    "other_daily_shift": other_shift
                }
    return integrated_dic
