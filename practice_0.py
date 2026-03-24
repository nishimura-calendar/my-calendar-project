import camelot
import pandas as pd
import pdfplumber
import re
import io

def pdf_reader(pdf_stream, target_staff):
    """PDFから2段構造（上段：記号、下段：時間）を考慮して自分と他人のシフトを抽出"""
    clean_target = re.sub(r'[\s　]', '', str(target_staff))
    
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
        
    tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    table_dictionary = {}
    
    for table in tables:
        df = table.df
        if df.empty: continue
            
        # 勤務地名抽出（A1セルの中央付近の行を取得）
        text = str(df.iloc[0, 0])
        lines = text.splitlines()
        target_index = text.count('\n') // 2
        work_place = lines[target_index] if target_index < len(lines) else (lines[-1] if lines else "unknown")
        
        # 名前列の空白を除去して検索
        search_col = df.iloc[:, 0].astype(str).str.replace(r'[\s　]', '', regex=True)
        matched_indices = df.index[search_col == clean_target].tolist()
        
        if matched_indices:
            idx = matched_indices[0]
            
            # --- 自分の2段データを抽出 ---
            if idx + 1 < len(df):
                my_daily_shift = df.iloc[idx : idx+2, :].copy()
            else:
                # 最終行の場合のガード
                my_daily_shift = df.iloc[idx : idx+1, :].copy()
                empty_row = pd.DataFrame([[''] * df.shape[1]], columns=df.columns)
                my_daily_shift = pd.concat([my_daily_shift, empty_row], ignore_index=True)
            
            # --- 他人のデータ（引き継ぎ解析用：名前がある行のみ） ---
            exclude_idx = [0, idx, idx + 1]
            other_daily_shift = df[~df.index.isin(exclude_idx)].copy()
            other_daily_shift = other_daily_shift[other_daily_shift.iloc[:, 0].str.strip() != ""].copy()

            my_daily_shift = my_daily_shift.reset_index(drop=True)
            other_daily_shift = other_daily_shift.reset_index(drop=True)
            
            table_dictionary[work_place] = [my_daily_shift, other_daily_shift]
            
    return table_dictionary

def extract_year_month(pdf_stream):
    """PDFから年月を抽出"""
    pdf_stream.seek(0)
    with pdfplumber.open(pdf_stream) as pdf:
        text = pdf.pages[0].extract_text()
        match = re.search(r'(\d{4})年\s*(\d{1,2})月', text)
        if match: return match.group(1), match.group(2)
    return "2026", "3"

def time_schedule_from_drive(service, file_id):
    """時程表Excelから時刻列の境界を判定して抽出"""
    from googleapiclient.http import MediaIoBaseDownload
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done: _, done = downloader.next_chunk()
    fh.seek(0)
    
    excel_data = pd.read_excel(fh, sheet_name=None, header=None, engine='openpyxl')
    location_data_dic = {}
    
    for sheet_name, full_df in excel_data.items():
        if full_df.empty: continue

        # 時刻（数値）が終わる列（col_limit）を判定
        col_limit = len(full_df.columns)
        for i in range(2, len(full_df.columns)):
            val = full_df.iloc[0, i]
            if pd.isna(val) or val == "":
                col_limit = i
                break
            try: float(val)
            except:
                col_limit = i
                break

        location_rows = full_df[full_df.iloc[:, 0].astype(str).str.strip() != ""].index.tolist()
        for i, start_row in enumerate(location_rows):
            end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
            location_name = str(full_df.iloc[start_row, 0]).strip()
            
            data_range = full_df.iloc[start_row:end_row, 0:col_limit].copy()
            data_range = data_range.reset_index(drop=True).astype(object)

            # 時間表記の変換
            for col in range(2, data_range.shape[1]):
                val = data_range.iloc[0, col]
                if pd.notna(val) and isinstance(val, (int, float)):
                    try:
                        hours = int(val * 24) if val < 1 else int(val)
                        minutes = int(round((val * 24 - hours) * 60)) if val < 1 else 0
                        data_range.iloc[0, col] = f"{hours}:{minutes:02d}"
                    except: continue
                
            data_range = data_range.fillna('')
            location_data_dic[location_name] = [data_range]
            
    return location_data_dic

def data_integration(pdf_dic, time_sched_dic):
    """場所名でPDFと時程表を統合"""
    integrated = {}
    clean_time_keys = {re.sub(r'[\s　]', '', k): (k, v) for k, v in time_sched_dic.items()}
    for pk, pv in pdf_dic.items():
        cpk = re.sub(r'[\s　]', '', pk)
        if cpk in clean_time_keys:
            orig_k, tv = clean_time_keys[cpk]
            integrated[pk] = pv + tv
    return integrated
