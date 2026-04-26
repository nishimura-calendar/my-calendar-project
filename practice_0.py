import pandas as pd
import re
import unicodedata
import os
import camelot

def normalize_text(text):
    """【打ち合わせ通り】正規化、空白除去、小文字化"""
    if not isinstance(text, str): return ""
    text = unicodedata.normalize('NFKC', text)
    return re.sub(r'[\s　]', '', text).lower()

def extract_year_month_from_text(text):
    """【打ち合わせ通り】ファイル名から年月を抽出"""
    if not text: return "2026", "04"
    text = unicodedata.normalize('NFKC', text)
    clean_text = re.sub(r'\s+', '', text)
    y_val, m_val = None, None
    month_match = re.search(r'(\d{1,2})月', clean_text)
    if month_match: m_val = int(month_match.group(1))
    nums = re.findall(r'\d+', clean_text)
    for n in nums:
        if len(n) == 4: y_val = int(n)
        elif len(n) == 2 and y_val is None: y_val = 2000 + int(n)
    return str(y_val or "2026"), str(m_val or "04")

def time_schedule_from_drive(sheets_service, file_id):
    """
    【consideration_0.pyを再現】
    A列を補完し、勤務地ごとに異なる時間軸構造を辞書として保持する。
    """
    try:
        spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=file_id).execute()
        sheets = spreadsheet.get('sheets', [])
        
        location_data_dic = {}
        for s in sheets:
            title = s.get("properties", {}).get("title")
            result = sheets_service.spreadsheets().values().get(
                spreadsheetId=file_id, range=f"'{title}'!A1:Z200").execute()
            
            vals = result.get('values', [])
            if not vals: continue
            
            # 各勤務地で列数が異なる可能性を考慮し、最大列数でパディング
            max_cols = max(len(row) for row in vals)
            padded_vals = [row + [''] * (max_cols - len(row)) for row in vals]
            df = pd.DataFrame(padded_vals)
            
            # --- 列名の重複回避（Streamlit表示用） ---
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
            
            # --- A列（勤務地）の空白をffillで補完 ---
            first_col = df.columns[0]
            df[first_col] = df[first_col].replace('', None).replace(' ', None).ffill()
            
            # --- 勤務地をキーに、その構造のまま辞書登録 ---
            for loc in df[first_col].unique():
                if not loc: continue
                # ここで勤務地ごとの時間軸（15分/20分等）が維持される
                location_data_dic[str(loc)] = df[df[first_col] == loc].fillna('').reset_index(drop=True)
                
        return location_data_dic
    except Exception as e:
        raise e

def pdf_reader(pdf_stream, target_staff):
    """
    【打ち合わせ通り】Camelotを使用して特定スタッフの2行と他スタッフを抽出。
    勤務地名、日付、曜日の整合性を保つ。
    """
    clean_target = normalize_text(target_staff)
    pdf_stream.seek(0)
    temp_name = "temp_process.pdf"
    with open(temp_name, "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    try:
        # latticeモードで表を精密に解析
        tables = camelot.read_pdf(temp_name, pages='all', flavor='lattice')
        res = {}
        for table in tables:
            df = table.df
            if df.empty: continue
            
            # 左上セルから勤務地を取得
            header = str(df.iloc[0, 0]).splitlines()
            work_place = header[len(header)//2] if header else "不明"
            
            # A列（スタッフ名列）からターゲットを検索
            search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
            matches = df.index[search_col == clean_target].tolist()
            
            if matches:
                idx = matches[0]
                # 打ち合わせ通り：自分のシフト（名前行と時間行の2行）
                my_daily = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
                # 打ち合わせ通り：他スタッフ（ヘッダーと自分以外）
                others = df.drop([0, idx, idx+1] if idx+1 < len(df) else [0, idx]).copy().reset_index(drop=True)
                
                res[work_place] = [my_daily, others]
        return res
    except:
        return {}
    finally:
        if os.path.exists(temp_name): os.remove(temp_name)
