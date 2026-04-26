import pandas as pd
import re
import unicodedata
import os
import camelot
import io
from googleapiclient.http import MediaIoBaseDownload

def normalize_text(text):
    if not isinstance(text, str): return ""
    text = unicodedata.normalize('NFKC', text)
    return re.sub(r'[\s　]', '', text).lower()

def extract_year_month_from_text(text):
    """ファイル名から年・月を抽出。見つからない場合はNoneを返し、後続で停止させる"""
    if not text: return None, None
    text = unicodedata.normalize('NFKC', text)
    y_match = re.search(r'(\d{4})', text)
    m_match = re.search(r'(\d{1,2})月', text)
    y = int(y_match.group(1)) if y_match else None
    m = int(m_match.group(1)) if m_match else None
    return y, m

def time_schedule_from_drive(service, file_id):
    """時程表を安全にエクスポートして取得"""
    try:
        # スプレッドシートをExcel形式でエクスポート
        request = service.files().export_media(
            fileId=file_id, 
            mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        fh.seek(0)
        
        # 構造を維持して読み込み
        full_df = pd.read_excel(fh, header=None, engine='openpyxl', dtype=str)
        
        location_rows = full_df[full_df.iloc[:, 0].notna()].index.tolist()
        location_data_dic = {}
        
        for i, start_row in enumerate(location_rows):
            end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
            location_name_raw = str(full_df.iloc[start_row, 0]).strip()
            norm_key = normalize_text(location_name_raw)
            if not norm_key or norm_key == 'nan': continue
            
            temp_range = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
            for col in range(len(temp_range.columns)):
                v = temp_range.iloc[0, col]
                try:
                    f_v = float(v)
                    if 0 <= f_v <= 28:
                        h = int(f_v); m = int(round((f_v - h) * 60))
                        temp_range.iloc[0, col] = f"{h}:{m:02d}"
                except: pass
            
            location_data_dic[norm_key] = {"df": temp_range.fillna(''), "original_name": location_name_raw}
        return location_data_dic
    except Exception as e:
        # ここで発生したエラーはapp.py側でキャッチして停止させる
        raise e

def pdf_reader(pdf_stream, target_staff, expected_days, time_master_dic):
    """PDFを解析し、不整合があれば空の辞書を返す"""
    clean_target = normalize_text(target_staff)
    pdf_stream.seek(0)
    temp_path = "temp_render.pdf"
    with open(temp_path, "wb") as f: f.write(pdf_stream.getbuffer())
    try:
        tables = camelot.read_pdf(temp_path, pages='all', flavor='lattice')
        res = {}
        for table in tables:
            df = table.df
            if df.empty: continue
            
            # 第2関門：日数チェック
            if (df.shape[1] - 1) != expected_days: continue

            raw_header = "".join(df.iloc[0, 0].splitlines())
            norm_header = normalize_text(raw_header)
            matched_key = next((k for k in time_master_dic.keys() if k in norm_header), None)
            if not matched_key: continue

            search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
            matches = df.index[search_col == clean_target].tolist()
            if matches:
                idx = matches[0]
                my_shift = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
                others = df.drop([0, idx, idx+1] if idx+1 < len(df) else [0, idx]).copy().reset_index(drop=True)
                res[matched_key] = [my_shift, others, time_master_dic[matched_key]["original_name"]]
        return res
    finally:
        if os.path.exists(temp_path): os.remove(temp_path)
