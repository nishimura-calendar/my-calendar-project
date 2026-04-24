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
    # row_tol=2 により、日付行(0)と勤務地・曜日行(1)を分離
    tables = camelot.read_pdf(
        "temp.pdf", pages='1', flavor='stream',
        columns=[str(l_boundary)], 
        row_tol=2, 
        strip_text='\n'
    )
    return tables[0].df if tables else None

def time_schedule_from_drive(sheet_id):
    """① 時程表をGoogle Sheetから取得 (勤務地をKeyとして辞書化)"""
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv"
    try:
        df = pd.read_csv(url)
        # 実際には時程表シート内の「勤務地」列で分ける
        # ここでは打ち合わせ通り、マスターとして返却
        return {"T2": df} 
    except Exception as e:
        st.error(f"時程表取得失敗: {e}")
        return {}

def data_integration(df_pdf, time_schedule_dic, target_staff):
    """② 時程表の勤務地を正として紐付け"""
    integrated_dic = {}
    clean_target = normalize_text(target_staff)
    
    # 【重要】勤務地は iloc[1, 0] から取得
    pdf_work_place = str(df_pdf.iloc[1, 0]).strip()

    # 時程表（マスター）のキーでループ
    for loc_key in time_schedule_dic.keys():
        # 時程表のキーがPDFの勤務地セルに含まれているか
        if loc_key in pdf_work_place:
            # 氏名を検索
            search_col = df_pdf.iloc[:, 0].astype(str).apply(normalize_text)
            matched = df_pdf.index[search_col == clean_target].tolist()
            
            if matched:
                idx = matched[0]
                # 本人の2行分と、それ以外のスタッフ（ヘッダー・本人以外）
                my_shift = df_pdf.iloc[idx : idx+2, :].copy()
                # 0,1,2行(ヘッダー)と本人行を除外
                other_shift = df_pdf.drop([0, 1, idx, idx+1], errors='ignore').copy()
                
                integrated_dic[loc_key] = {
                    "time_schedule": time_schedule_dic[loc_key],
                    "my_daily_shift": my_shift,
                    "other_daily_shift": other_shift
                }
    return integrated_dic
