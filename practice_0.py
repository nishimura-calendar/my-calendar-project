import pandas as pd
import re
import unicodedata
import os
import camelot
import calendar

def normalize_text(text):
    """打ち合わせ内容：正規化・空白除去・小文字化"""
    if not isinstance(text, str): return ""
    text = unicodedata.normalize('NFKC', text)
    return re.sub(r'[\s　]', '', text).lower()

def extract_year_month_from_text(text):
    """ファイル名（正）から年・月・日数・第1曜日を算出"""
    if not text: return "2026", "04", 30, 0
    text = unicodedata.normalize('NFKC', text)
    y_val, m_val = 2026, 4
    
    m_match = re.search(r'(\d{1,2})月', text)
    if m_match: m_val = int(m_match.group(1))
    y_match = re.search(r'(\d{4})', text)
    if y_match: y_val = int(y_match.group(1))
    
    days_in_month = calendar.monthrange(y_val, m_val)[1]
    first_weekday = calendar.monthrange(y_val, m_val)[0]
    
    return str(y_val), str(m_val), days_in_month, first_weekday

def time_schedule_from_drive(sheets_service, file_id):
    """
    consideration_0.py準拠：
    時程表(マスター)を読み込み、A列を補完して勤務地をキーに辞書化。
    """
    spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=file_id).execute()
    sheets = spreadsheet.get('sheets', [])
    location_data_dic = {}
    
    for s in sheets:
        title = s.get("properties", {}).get("title")
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=file_id, range=f"'{title}'!A1:Z200").execute()
        vals = result.get('values', [])
        if not vals: continue
        
        max_cols = max(len(row) for row in vals)
        df = pd.DataFrame([row + [''] * (max_cols - len(row)) for row in vals])
        
        # 重複列名回避
        raw_cols = [str(c).strip() if c else f"Unnamed_{i}" for i, c in enumerate(df.iloc[0])]
        new_cols = []
        counts = {}
        for col in raw_cols:
            if col in counts:
                counts[col] += 1
                new_cols.append(f"{col}_{counts[col]}")
            else:
                counts[col] = 0
                new_cols.append(col)
        df.columns = new_cols
        df = df[1:].reset_index(drop=True)
        
        # A列(勤務地)補完
        first_col = df.columns[0]
        df[first_col] = df[first_col].replace('', None).replace(' ', None).ffill()
        
        for loc in df[first_col].unique():
            if not loc: continue
            location_data_dic[normalize_text(str(loc))] = df[df[first_col] == loc].fillna('').reset_index(drop=True)
            
    return location_data_dic

def pdf_reader(pdf_stream, target_staff, expected_days, time_master_keys):
    """
    打ち合わせ通り：Camelot解析。
    第1関門(勤務地確認)と第2関門(日程整合性)を判定。
    """
    clean_target = normalize_text(target_staff)
    pdf_stream.seek(0)
    temp_name = "temp_process.pdf"
    with open(temp_name, "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    try:
        tables = camelot.read_pdf(temp_name, pages='all', flavor='lattice')
        if not tables:
            return {"error_type": "SYSTEM", "msg": "PDFから表を抽出できませんでした。"}

        res = {}
        for table in tables:
            df = table.df
            if df.empty: continue
            
            # PDFから勤務地を特定
            header = str(df.iloc[0, 0]).splitlines()
            work_place_raw = header[len(header)//2] if header else "Unknown"
            norm_wp = normalize_text(work_place_raw)
            
            # 【第1関門】勤務地が時程表(正)に存在するか
            if norm_wp not in time_master_keys:
                return {"error_type": "WP_MISSING", "wp": work_place_raw}

            # 【第2関門】日程不一致の確認 (スタッフ名列を除いた列数)
            pdf_days = df.shape[1] - 1 
            if pdf_days != expected_days:
                return {"error_type": "DAY_MISMATCH", "exp": expected_days, "act": pdf_days}

            # スタッフ抽出
            search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
            matches = df.index[search_col == clean_target].tolist()
            
            if matches:
                idx = matches[0]
                my_shift = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
                others = df.drop([0, idx, idx+1] if idx+1 < len(df) else [0, idx]).copy().reset_index(drop=True)
                res[norm_wp] = [my_shift, others, work_place_raw]
        
        return res if res else {"error_type": "SYSTEM", "msg": f"『{target_staff}』さんが見つかりません。"}
    except Exception as e:
        return {"error_type": "SYSTEM", "msg": str(e)}
    finally:
        if os.path.exists(temp_name): os.remove(temp_name)
