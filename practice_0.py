import pandas as pd
import camelot
import unicodedata
import re
import io
import calendar
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload

# --- 1. テキストの正規化 (名前や勤務地を正しく照合するため) ---
def normalize_text(text):
    if not isinstance(text, str): return ""
    # 空白、改行をすべて除去
    return re.sub(r'[\s　\n\r\t]', '', unicodedata.normalize('NFKC', text)).lower()

# --- 2. 年月の抽出 (ファイル名を「正」としてそこから情報を取る) ---
def extract_year_month_from_text(text):
    if not text: return None, None
    text = unicodedata.normalize('NFKC', text)
    clean_text = re.sub(r'\s+', '', text)
    y_val, m_val = None, None
    
    # 月の特定
    month_match = re.search(r'(\d{1,2})月', clean_text)
    if month_match:
        m_val = int(month_match.group(1))
    
    # 年の特定
    nums = re.findall(r'\d+', clean_text)
    for n in nums:
        val = int(n)
        if len(n) == 4:
            y_val = val
            break
        elif len(n) == 2 and y_val is None:
            y_val = 2000 + val
            
    return y_val, m_val

# --- 3. PDF解析メイン (指定されたファイルを直接処理) ---
def pdf_reader(pdf_stream, target_staff, file_name=""):
    """
    選ばれたPDF(pdf_stream)を、ファイル名(file_name)の情報に基づいて解析する。
    """
    clean_target = normalize_text(target_staff)
    pdf_stream.seek(0)
    
    # ファイル名から「正解の年月」を取得
    year, month = extract_year_month_from_text(file_name)
    
    # カレンダーの正解（1日の曜日と日数）を計算
    if year and month:
        first_wday_idx, last_day = calendar.monthrange(year, month)
        weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
        expected_first_wday = weekdays_jp[first_wday_idx]
    else:
        # ファイル名から年月が取れない場合は、PDF全体を探す必要が出てしまうため、
        # ここでは「指定ファイルが不明」として扱う
        return {}, None, None

    # 一時ファイルとして書き出し（Camelot用）
    temp_path = "target_shift.pdf"
    with open(temp_path, "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    try:
        # 指定されたPDFの全ページを格子状(lattice)で読み込む
        tables = camelot.read_pdf(temp_path, pages='all', flavor='lattice')
    except:
        return {}, year, month

    table_dictionary = {}
    
    for table in tables:
        df = table.df
        if df.empty: continue
        
        # --- 勤務地・日付行（0行目）の抽出 ---
        # 0行0列目から勤務地名を特定
        header_raw = str(df.iloc[0, 0])
        header_lines = header_raw.splitlines()
        work_place = header_lines[len(header_lines)//2].strip() if header_lines else "Unknown"
        
        # 0行目の右側から日付と曜日を取得
        pdf_days = []
        for col in range(1, df.shape[1]):
            val = normalize_text(str(df.iloc[0, col]))
            d_m = re.search(r'(\d+)', val)
            w_m = re.search(r'([月火水木金土日])', val)
            if d_m and w_m:
                pdf_days.append({"d": int(d_m.group(1)), "w": w_m.group(1)})
        
        # 整合性チェック：この表がファイル名の年月と一致しているか
        if not pdf_days: continue
        if pdf_days[0]["w"] != expected_first_wday or pdf_days[-1]["d"] != last_day:
            # カレンダーが一致しない表（前後の月の表など）は飛ばす
            continue

        # --- 名前検索とデータ抽出 ---
        search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
        # 部分一致で検索（PDF内のゴミデータを許容）
        matched_indices = [i for i, v in enumerate(search_col) if clean_target in v]
        
        if matched_indices:
            idx = matched_indices[0]
            # 【基本ルール】自分は2行、他人は1行で抽出
            my_daily = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
            others = df.drop([0, idx, idx+1] if idx+1 < len(df) else [0, idx]).copy().reset_index(drop=True)
            
            table_dictionary[work_place] = [my_daily, others]
                
    return table_dictionary, year, month

# --- 4. スプレッドシート取得関数 ---
def fetch_time_schedule(service, spreadsheet_id):
    try:
        request = service.files().export_media(fileId=spreadsheet_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        fh.seek(0)
        return pd.read_excel(fh, header=None, engine='openpyxl').fillna('')
    except:
        return pd.DataFrame()
