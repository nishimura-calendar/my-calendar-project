import pandas as pd
import camelot
import re
import unicodedata
import calendar
import streamlit as st

def normalize_text(text):
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def extract_year_month_from_text(text):
    text = unicodedata.normalize('NFKC', text)
    m_match = re.search(r'(\d{1,2})月', text)
    y_match = re.search(r'(\d{4})年', text)
    y_val = int(y_match.group(1)) if y_match else 2026 # デフォルト
    m_val = int(m_match.group(1)) if m_match else None
    return y_val, m_val

def pdf_reader_engine(uploaded_pdf, l_boundary):
    """打ち合わせ通りの座標定義でPDFを読み込む"""
    with open("temp.pdf", "wb") as f:
        f.write(uploaded_pdf.getbuffer())
    
    tables = camelot.read_pdf(
        "temp.pdf", pages='1', flavor='stream',
        columns=[str(l_boundary)], # 中線のx座標(l)
        row_tol=2,                 # 文字高さ(h)で分解
        strip_text='\n'
    )
    return tables[0].df if tables else None

def time_schedule_from_drive(sheet_id):
    """① 時程表をGoogle Sheetから取得 (勤務地がKey)"""
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv"
    try:
        all_data = pd.read_csv(url)
        # 実際には「勤務地」ごとに分割するロジックが必要
        # ここでは例としてT2をキーにした辞書を作成
        dic = {"T2": all_data} 
        return dic
    except Exception as e:
        st.error(f"時程表取得失敗: {e}")
        return {}

def data_integration(df_pdf, time_schedule_dic, target_staff):
    """② PDFシフトと時程表を紐付け (時程表の勤務地が正)"""
    integrated_dic = {}
    clean_target = normalize_text(target_staff)
    
    # PDF内の勤務地候補(A1セル付近)を取得
    pdf_work_place = str(df_pdf.iloc[1, 0]).strip()

    # 時程表(Master)にある勤務地だけを処理対象にする
    for loc_key in time_schedule_dic.keys():
        if loc_key in pdf_work_place:
            # スタッフを探してシフトを抽出
            search_col = df_pdf.iloc[:, 0].astype(str).apply(normalize_text)
            matched = df_pdf.index[search_col == clean_target].tolist()
            
            if matched:
                idx = matched[0]
                my_shift = df_pdf.iloc[idx : idx+2, :].copy()
                other_shift = df_pdf.drop([0, 1, 2, idx, idx+1], errors='ignore').copy()
                
                # 紐付け登録
                integrated_dic[loc_key] = {
                    "time_schedule": time_schedule_dic[loc_key],
                    "my_daily_shift": my_shift,
                    "other_daily_shift": other_shift
                }
    
    return integrated_dic
