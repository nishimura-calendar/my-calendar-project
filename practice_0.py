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
        
        first_col = df.columns[0]
        df[first_col] = df[first_col].replace('', None).replace(' ', None).ffill()
        
        for loc in df[first_col].unique():
            if pd.isna(loc) or str(loc).strip() == "" or str(loc).lower() == 'nan': continue
            norm_key = normalize_text(str(loc))
            location_data_dic[norm_key] = {
                "df": df[df[first_col] == loc].fillna('').reset_index(drop=True),
                "original_name": str(loc)
            }
    return location_data_dic

def pdf_reader(pdf_stream, target_staff, expected_days, time_master_dic):
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
        # マスターのキーを長さ順（降順）にソート（T10がT1に誤判定されるのを防ぐ）
        master_keys = sorted(time_master_dic.keys(), key=len, reverse=True)

        for table in tables:
            df = table.df
            if df.empty: continue
            
            raw_header_text = "".join(df.iloc[0, 0].splitlines())
            norm_header = normalize_text(raw_header_text)
            
            matched_key = None
            for m_key in master_keys:
                if m_key in norm_header:
                    matched_key = m_key
                    break
            
            if not matched_key:
                return {"error_type": "WP_MISSING", "wp": raw_header_text}

            pdf_days = df.shape[1] - 1 
            if pdf_days != expected_days:
                return {"error_type": "DAY_MISMATCH", "exp": expected_days, "act": pdf_days}

            search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
            matches = df.index[search_col == clean_target].tolist()
            
            if matches:
                idx = matches[0]
                my_shift = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
                others = df.drop([0, idx, idx+1] if idx+1 < len(df) else [0, idx]).copy().reset_index(drop=True)
                res[matched_key] = [my_shift, others, time_master_dic[matched_key]["original_name"]]
        
        return res if res else {"error_type": "SYSTEM", "msg": f"『{target_staff}』さんが見つかりません。"}
    except Exception as e:
        return {"error_type": "SYSTEM", "msg": str(e)}
    finally:
        if os.path.exists(temp_name): os.remove(temp_name)
