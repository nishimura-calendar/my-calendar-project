import pandas as pd
import re
import unicodedata
import os
import camelot
import io
from googleapiclient.http import MediaIoBaseDownload

def normalize_text(text):
    """比較用に文字を正規化（全角半角統一・空白除去・小文字化）"""
    if not isinstance(text, str): return ""
    text = unicodedata.normalize('NFKC', text)
    return re.sub(r'[\s　]', '', text).lower()

def extract_year_month_from_text(text):
    """
    ファイル名から年・月を『探す』だけの関数。
    戻り値: (year, month)  ※見つからない場合は None
    """
    if not text: return None, None
    text = unicodedata.normalize('NFKC', text)
    
    y_match = re.search(r'(\d{4})', text)
    m_match = re.search(r'(\d{1,2})月', text)
    
    y = y_match.group(1) if y_match else None
    m = m_match.group(1) if m_match else None
    
    return y, m

def time_schedule_from_drive(service, file_id):
    """時程表スプレッドシートを構造を維持して読み込む"""
    try:
        file_metadata = service.files().get(fileId=file_id, fields='mimeType').execute()
        request = service.files().get_media(fileId=file_id)
        if file_metadata.get('mimeType') == 'application/vnd.google-apps.spreadsheet':
            request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done: _, done = downloader.next_chunk()
        fh.seek(0)
        
        full_df = pd.read_excel(fh, header=None, engine='openpyxl', sheet_name=0, dtype=str)
        location_rows = full_df[full_df.iloc[:, 0].notna()].index.tolist()
        location_data_dic = {}
        
        for i, start_row in enumerate(location_rows):
            end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
            location_name_raw = str(full_df.iloc[start_row, 0]).strip()
            norm_key = normalize_text(location_name_raw)
            if not norm_key or norm_key == 'nan': continue
            
            temp_range = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
            
            # 数値列(6.25等)を時刻形式(6:15)に整形
            for col in range(len(temp_range.columns)):
                v = temp_range.iloc[0, col]
                try:
                    f_v = float(v)
                    if 0 <= f_v <= 28:
                        h = int(f_v)
                        m = int(round((f_v - h) * 60))
                        temp_range.iloc[0, col] = f"{h}:{m:02d}"
                except: pass
            
            location_data_dic[norm_key] = {
                "df": temp_range.fillna(''),
                "original_name": location_name_raw
            }
        return location_data_dic
    except Exception as e:
        raise e

def pdf_reader(pdf_stream, target_staff, expected_days, time_master_dic):
    """PDFからスタッフのシフトを抽出"""
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
        master_keys = sorted(time_master_dic.keys(), key=len, reverse=True)

        for table in tables:
            df = table.df
            if df.empty: continue
            
            raw_header = "".join(df.iloc[0, 0].splitlines())
            norm_header = normalize_text(raw_header)
            
            matched_key = None
            for key in master_keys:
                if key in norm_header:
                    matched_key = key
                    break
            
            if not matched_key: continue

            # 日数チェック（ユーザーが入力した日数と照合）
            pdf_days = df.shape[1] - 1 
            if pdf_days != expected_days:
                return {"error_type": "DAY_MISMATCH", "act": pdf_days}

            search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
            matches = df.index[search_col == clean_target].tolist()
            
            if matches:
                idx = matches[0]
                my_shift = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
                others = df.drop([0, idx, idx+1] if idx+1 < len(df) else [0, idx]).copy().reset_index(drop=True)
                res[matched_key] = [my_shift, others, time_master_dic[matched_key]["original_name"]]
        
        return res if res else {"error_type": "NOT_FOUND", "msg": f"『{target_staff}』さんが見つかりません。"}
    finally:
        if os.path.exists(temp_name): os.remove(temp_name)
