import pandas as pd
import re
import unicodedata
import os
import camelot
import calendar

def normalize_text(text):
    """全角半角を統一し、空白を除去して小文字化（照合用）"""
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
    """時程表(マスター)を読み込み、A列をキーに辞書化。"""
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
            if pd.isna(loc) or str(loc).strip() == "": continue
            norm_key = normalize_text(str(loc))
            location_data_dic[norm_key] = {
                "df": df[df[first_col] == loc].fillna('').reset_index(drop=True),
                "original_name": str(loc)
            }
            
    return location_data_dic

def pdf_reader(pdf_stream, target_staff, expected_days, time_master_dic):
    """PDF解析。第1関門(勤務地確認)と第2関門(日程整合性)を判定。"""
    clean_target = normalize_text(target_staff)
    pdf_stream.seek(0)
    temp_name = "temp_process.pdf"
    with open(temp_name, "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    try:
        # PDF内の全テーブルを格子モードで取得
        tables = camelot.read_pdf(temp_name, pages='all', flavor='lattice')
        if not tables:
            return {"error_type": "SYSTEM", "msg": "PDFから表を抽出できませんでした。"}

        res = {}
        master_keys = time_master_dic.keys()

        for table in tables:
            df = table.df
            if df.empty: continue
            
            # PDFから勤務地を抽出。改行や不要な文字を結合して正規化
            raw_header_text = "".join(df.iloc[0, 0].splitlines())
            norm_header = normalize_text(raw_header_text)
            
            # 【第1関門の訂正】
            # マスターのキー（例: "t1"）が、PDFの長い見出しの中に独立して含まれているか判定
            matched_key = None
            for m_key in master_keys:
                # 単に含むだけでなく、前後が数字や曜日で汚れていても見つけ出せるようにします
                if m_key in norm_header:
                    matched_key = m_key
                    break
            
            if not matched_key:
                return {"error_type": "WP_MISSING", "wp": raw_header_text}

            # 【第2関門】日程不一致の確認
            pdf_days = df.shape[1] - 1 
            if pdf_days != expected_days:
                return {"error_type": "DAY_MISMATCH", "exp": expected_days, "act": pdf_days}

            # スタッフ抽出
            search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
            matches = df.index[search_col == clean_target].tolist()
            
            if matches:
                idx = matches[0]
                # 自分の2行
                my_shift = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
                # 自分以外のスタッフ（ヘッダーを除く）
                others = df.drop([0, idx, idx+1] if idx+1 < len(df) else [0, idx]).copy().reset_index(drop=True)
                res[matched_key] = [my_shift, others, time_master_dic[matched_key]["original_name"]]
        
        if not res:
            return {"error_type": "SYSTEM", "msg": f"『{target_staff}』さんのデータが見つかりませんでした。"}
            
        return res
    except Exception as e:
        return {"error_type": "SYSTEM", "msg": str(e)}
    finally:
        if os.path.exists(temp_name): os.remove(temp_name)
