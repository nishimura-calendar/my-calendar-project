import pandas as pd
import re
import unicodedata
import os
import camelot
import calendar

def normalize_text(text):
    if not isinstance(text, str): return ""
    text = unicodedata.normalize('NFKC', text)
    return re.sub(r'[\s　]', '', text).lower()

def extract_year_month_from_text(text):
    """
    【ファイル名=正】
    ファイル名から「年」と「月」を抽出し、
    その年月に基づく「正確な日数」と「第一曜日」を算出する。
    """
    if not text: return None
    text = unicodedata.normalize('NFKC', text)
    clean_text = re.sub(r'\s+', '', text)
    
    # 年(4桁)と月(1-2桁)を抽出
    y_match = re.search(r'(\d{4})', clean_text)
    m_match = re.search(r'(\d{1,2})月', clean_text)
    
    if not y_match or not m_match:
        return None

    y_val = int(y_match.group(1))
    m_val = int(m_match.group(1))
    
    # 指定された年月の情報を取得
    # monthrangeは (その月の最初の日の曜日, その月の日数) を返す
    # 曜日: 0=月, 1=火, 2=水, 3=木, 4=金, 5=土, 6=日
    first_wd_num, days_in_month = calendar.monthrange(y_val, m_val)
    
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    expected_first_wd = weekdays_jp[first_wd_num]
    
    return {
        "year": y_val,
        "month": m_val,
        "days": days_in_month,
        "first_wd": expected_first_wd
    }

def pdf_reader(pdf_stream, target_staff, expected_info):
    """
    【第二関門】
    iloc[]座標指定により、ファイル名から導かれた「年・月」の基準と、
    PDF内の「日数・曜日」が完全に一致するか照合する。
    """
    pdf_stream.seek(0)
    temp_name = "temp_process.pdf"
    with open(temp_name, "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    try:
        tables = camelot.read_pdf(temp_name, pages='all', flavor='lattice')
        res = {}
        
        for table in tables:
            df = table.df
            if df.empty: continue
            
            # --- 第一関門: 勤務地 (iloc[0,0]の中央行) ---
            cell_0_0 = str(df.iloc[0, 0])
            lines = cell_0_0.splitlines()
            target_index = cell_0_0.count('\n') // 2
            work_place = lines[target_index] if target_index < len(lines) else "unknown"
            
            # --- 第二関門: 座標指定チェック ---
            # 1. 日数確認: iloc[0, 最終列]
            pdf_days_val = str(df.iloc[0, -1]).strip()
            # 2. 第一曜日確認: iloc[1, 1]
            pdf_first_wd = str(df.iloc[1, 1]).strip()
            
            # 判定（年月の期待値と比較）
            is_days_match = (pdf_days_val == str(expected_info["days"]))
            is_wd_match = (pdf_first_wd == expected_info["first_wd"])
            
            if not is_days_match or not is_wd_match:
                # 不一致の場合、詳細な理由を返して終了
                error_msg = (
                    f"【第二関門不通過】ファイル名と中身が一致しません。\n"
                    f"原因: ファイル名からは {expected_info['year']}年{expected_info['month']}月 "
                    f"({expected_info['days']}日間 / 1日={expected_info['first_wd']}) を想定しましたが、\n"
                    f"PDFの座標(iloc)には {pdf_days_val}日間 / 1日={pdf_first_wd} と記載されています。"
                )
                return {"error": error_msg, "df_for_display": df}

            # --- 第三関門: スタッフ抽出 ---
            clean_target = normalize_text(target_staff)
            search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
            matches = df.index[search_col == clean_target].tolist()
            
            if matches:
                idx = matches[0]
                my_shift = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
                others = df.drop([0, idx, idx+1] if idx+1 < len(df) else [0, idx]).copy().reset_index(drop=True)
                res[normalize_text(work_place)] = [my_shift, others, work_place]
        
        return res
    finally:
        if os.path.exists(temp_name):
            os.remove(temp_name)
