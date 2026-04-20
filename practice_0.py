import pandas as pd
import camelot
import unicodedata
import re
import io
import calendar
import pdfplumber
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload

# --- 共通ユーティリティ (consideration_0.py準拠) ---
def normalize_text(text):
    """テキストの正規化（全角→半角、空白除去）"""
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def extract_year_month_from_text(text):
    """PDFテキストから年月を抽出"""
    if not text: return None, None
    text = unicodedata.normalize('NFKC', text)
    clean_text = re.sub(r'\s+', '', text)
    y_val, m_val = None, None
    
    # 「〇月」を探す
    month_match = re.search(r'(\d{1,2})月', clean_text)
    if month_match:
        m_val = int(month_match.group(1))
    
    # 数値をすべて抽出して年を特定
    nums = re.findall(r'\d+', clean_text)
    for n in nums:
        val = int(n)
        if len(n) == 4:
            y_val = val
        elif len(n) == 2:
            if m_val is None or (val != m_val):
                if y_val is None:
                    y_val = 2000 + val
                    
    if m_val is None:
        for n in nums:
            val = int(n)
            if 1 <= val <= 12 and (y_val is None or val != (y_val % 100)):
                m_val = val
                break
    return y_val, m_val

# --- Google Drive / Sheets 連携 (consideration_0.py準拠) ---
def get_gdrive_service(secrets):
    creds = service_account.Credentials.from_service_account_info(
        secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build('drive', 'v3', credentials=creds)

def time_schedule_from_drive(service, file_id):
    """時程表（スプレッドシート）を勤務地別の辞書として取得"""
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
        
        # openpyxlで読み込み
        full_df = pd.read_excel(fh, header=None, engine='openpyxl', sheet_name=0, dtype=str)
        location_rows = full_df[full_df.iloc[:, 0].notna()].index.tolist()
        location_data_dic = {}
        
        for i, start_row in enumerate(location_rows):
            end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
            location_name = str(full_df.iloc[start_row, 0]).strip()
            temp_range = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
            
            # 時程行（数値列）の特定
            time_row = temp_range.iloc[0, :]
            first_num_col = None
            last_num_col = None
            for col_idx, val in enumerate(time_row):
                if col_idx < 1: continue 
                try:
                    float(val)
                    if first_num_col is None: first_num_col = col_idx
                    last_num_col = col_idx
                except: continue
            
            if first_num_col is not None:
                start_col = max(1, first_num_col - 1)
                end_col = last_num_col + 1
                fixed_cols = [0, 1] 
                target_cols = fixed_cols + list(range(start_col, end_col))
                temp_range = temp_range.iloc[:, target_cols].copy()
                
                # シリアル値を時刻文字列(H:MM)に変換
                for col in range(len(temp_range.columns)):
                    if col < 2: continue
                    v = temp_range.iloc[0, col]
                    try:
                        f_v = float(v)
                        if 0 <= f_v <= 28:
                            h = int(f_v)
                            m = int(round((f_v - h) * 60))
                            temp_range.iloc[0, col] = f"{h}:{m:02d}"
                    except: pass
            
            location_data_dic[location_name] = temp_range.fillna('')
        return location_data_dic
    except Exception as e:
        raise e

# --- PDF解析 (consideration_0.py準拠 + Camelot) ---
def pdf_reader(pdf_stream, target_staff):
    """Camelotを使用して全ページをスキャンし、ターゲットのシフトを抽出"""
    clean_target = normalize_text(target_staff)
    pdf_stream.seek(0)
    temp_filename = "target_shift.pdf"
    with open(temp_filename, "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    # pdfplumberで1ページ目から年月を特定
    year, month = None, None
    with pdfplumber.open(temp_filename) as pdf:
        if len(pdf.pages) > 0:
            first_page_text = pdf.pages[0].extract_text()
            year, month = extract_year_month_from_text(first_page_text)

    try:
        # pages='all' で全ページ対応、latticeモード
        tables = camelot.read_pdf(temp_filename, pages='all', flavor='lattice')
    except:
        return {}, year, month

    table_dictionary = {}
    for table in tables:
        df = table.df
        if df.empty: continue
        
        # 勤務地の特定（左上セルの改行中央行）
        header_lines = str(df.iloc[0, 0]).splitlines()
        work_place = header_lines[len(header_lines)//2] if header_lines else "Unknown"
        
        # 名前検索
        search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
        matched_indices = df.index[search_col == clean_target].tolist()
        
        if matched_indices:
            idx = matched_indices[0]
            # [自分, 他の人] のペアで保存
            my_row = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
            others = df.drop([0, idx, idx+1] if idx+1 < len(df) else [0, idx]).copy().reset_index(drop=True)
            table_dictionary[work_place] = [my_row, others]
                
    return table_dictionary, year, month

# --- データ統合 (consideration_0.py準拠) ---
def data_integration(pdf_dic, time_dic):
    """PDF解析結果と時程表を勤務地キーで紐付け"""
    integrated = {}
    for pk, pv in pdf_dic.items():
        # 曖昧一致で勤務地を特定
        match = next((k for k in time_dic.keys() if normalize_text(pk) in normalize_text(k)), None)
        if match:
            # 形式: [my_row, others, time_schedule_df]
            integrated[match] = pv + [time_dic[match]]
    return integrated, []
