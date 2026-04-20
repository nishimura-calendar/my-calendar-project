import pandas as pd
import camelot
import unicodedata
import re
import io
import calendar
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload

# --- 1. テキストの正規化 (名前や勤務地を確実に一致させる) ---
def normalize_text(text):
    if not isinstance(text, str): return ""
    # 空白、全角スペース、改行、タブをすべて除去して比較
    return re.sub(r'[\s　\n\r\t]', '', unicodedata.normalize('NFKC', text)).lower()

# --- 2. ファイル名からの年月抽出 (ファイル名を「正」とする) ---
def extract_year_month_from_text(text):
    if not text: return None, None
    text = unicodedata.normalize('NFKC', text)
    # ファイル名から余計な空白を詰める
    clean_text = re.sub(r'\s+', '', text)
    y_val, m_val = None, None
    
    # 「○月」を検索
    month_match = re.search(r'(\d{1,2})月', clean_text)
    if month_match:
        m_val = int(month_match.group(1))
    
    # 4桁（西暦）または2桁を検索
    nums = re.findall(r'\d+', clean_text)
    for n in nums:
        val = int(n)
        if len(n) == 4:
            y_val = val
            break
        elif len(n) == 2 and y_val is None:
            # 2桁の場合は2000年代と仮定
            y_val = 2000 + val
            
    return y_val, m_val

# --- 3. PDF解析メイン (アップロードされたファイルを直接開く) ---
def pdf_reader(pdf_stream, target_staff, file_name=""):
    """
    ユーザーが選択したファイル名 (file_name) を取得し、その情報を基準に
    pdf_stream (アップロードされたファイルの中身) を直接開いて解析する。
    """
    clean_target = normalize_text(target_staff)
    pdf_stream.seek(0)
    
    # 1. ファイル名から「期待される年月」を確定（これが全ての基準）
    year, month = extract_year_month_from_text(file_name)
    
    if year and month:
        # 正解のカレンダー（1日の曜日と日数）を算出
        first_wday_idx, last_day = calendar.monthrange(year, month)
        weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
        expected_first_wday = weekdays_jp[first_wday_idx]
    else:
        # ファイル名に年月が含まれない場合は解析を中断（基本ルール）
        return {}, None, None

    # Camelot読み込み用に一時ファイルとして保存
    temp_path = "current_upload.pdf"
    with open(temp_path, "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    try:
        # 「クリックしたファイル」を全ページ読み込む
        tables = camelot.read_pdf(temp_path, pages='all', flavor='lattice')
    except Exception:
        return {}, year, month

    table_dictionary = {}
    
    for table in tables:
        df = table.df
        if df.empty: continue
        
        # --- 勤務地行（0行目）の解析 ---
        # 0行0列目: 勤務地名
        header_cell = str(df.iloc[0, 0])
        header_lines = header_cell.splitlines()
        # consideration_0.py のルールに従い中央行を勤務地とする
        work_place = header_lines[len(header_lines)//2].strip() if header_lines else "Unknown"
        
        # 0行目: 日付と曜日の並びを確認
        pdf_days = []
        for col in range(1, df.shape[1]):
            val = normalize_text(str(df.iloc[0, col]))
            d_m = re.search(r'(\d+)', val) # 日付
            w_m = re.search(r'([月火水木金土日])', val) # 曜日
            if d_m and w_m:
                pdf_days.append({"d": int(d_m.group(1)), "w": w_m.group(1)})
        
        # 整合性チェック: ファイル名のカレンダー条件と一致するか？
        if not pdf_days: continue
        # 1日の曜日が期待通りか、かつ末尾の日付がカレンダー通りか
        if pdf_days[0]["w"] != expected_first_wday or pdf_days[-1]["d"] != last_day:
            continue

        # --- 指定された名前の検索 (部分一致) ---
        search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
        matched_indices = [i for i, v in enumerate(search_col) if clean_target in v]
        
        if matched_indices:
            idx = matched_indices[0]
            # 【基本ルール】自分は2行、他人は1行で抽出
            my_daily = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
            # 0行目（日付）と自分(idx, idx+1)を除いた他人のシフト
            others = df.drop([0, idx, idx+1] if idx+1 < len(df) else [0, idx]).copy().reset_index(drop=True)
            
            table_dictionary[work_place] = [my_daily, others]
                
    return table_dictionary, year, month

# --- 4. Googleスプレッドシート連携 ---
def get_sheets_service(secrets):
    creds = service_account.Credentials.from_service_account_info(
        secrets["gcp_service_account"],
        scopes=['https://www.googleapis.com/auth/spreadsheets.readonly', 'https://www.googleapis.com/auth/drive.readonly']
    )
    return build('drive', 'v3', credentials=creds)

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

# --- 5. CSV用データ構成（枠組み） ---
def build_calendar_df(integrated_dic, year, month):
    # 打合.pyのロジックを統合してCSV行を生成する
    return []
