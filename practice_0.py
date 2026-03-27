import pandas as pd
import camelot
import io
import re
import pdfplumber
import unicodedata
from googleapiclient.http import MediaIoBaseDownload

# --- 1. 時間整形関数：数値やシリアル値を「HH:MM」に変換 ---
def format_to_hhmm(val):
    try:
        if val == "" or str(val).lower() == "nan": 
            return ""
        num = float(val)
        h = int(num * 24 if num < 1 else num)
        m = int(round((num * 24 - h) * 60 if num < 1 else (num - h) * 60))
        return f"{h:02d}:{m:02d}"
    except:
        return str(val).strip()

# --- 2. 特殊抽出関数：備考欄(v2)から「開始@終了」を抜き出す ---
def parse_special_shift(text):
    if not text or str(text).lower() == 'nan' or text == "":
        return "", "", False
    match = re.search(r'([\d\.:]+)\s*@\s*([\d\.:]+)', str(text))
    if match:
        def _adjust(t_str):
            t_str = t_str.replace('.', ':')
            if ':' in t_str:
                h, m = t_str.split(':')
                return f"{int(h):02d}:{int(m) if m else 0:02d}"
            else:
                return f"{int(t_str):02d}:00"
        return _adjust(match.group(1)), _adjust(match.group(2)), True
    return "", "", False

# --- 3. ドライブ取得関数：時程表を読み込み、時間を事前変換 ---
def time_schedule_from_drive(service, file_id):
    request = service.files().export_media(fileId=file_id, mimeType='text/csv')
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    full_df = pd.read_csv(fh, header=None).fillna('')

    location_data_dic = {}
    loc_idx = full_df[full_df.iloc[:, 0] != ""].index.tolist()
    for i, start_row in enumerate(loc_idx):
        loc_name = str(full_df.iloc[start_row, 0]).strip()
        end_row = loc_idx[i+1] if i+1 < len(loc_idx) else len(full_df)
        df = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
        # 3列目以降、全ての列の時間軸（1行目）を変換
        for col in range(2, df.shape[1]):
            df.iloc[0, col] = format_to_hhmm(df.iloc[0, col])
        location_data_dic[loc_name] = df
    return location_data_dic

# --- 4. 年月抽出関数 ---
def extract_year_month(pdf_stream):
    """PDFテキストから年月(20XX年XX月)を抽出"""
    try:
        with pdfplumber.open(pdf_stream) as pdf:
            # 1ページ目のテキストを取得
            text = pdf.pages[0].extract_text()
            if not text:
                return "2025", "3" # テキストが取れない場合のデフォルト
            
            # 正規表現の修正: \20 ではなく 20 と記述
            match = re.search(r'(20\d{2})年\s*(\d{1,2})月', text)
            if match:
                return match.group(1), match.group(2)
            
            # 別パターンの検索 (2025/03 など)
            match_alt = re.search(r'(20\d{2})[/\s](\d{1,2})', text)
            if match_alt:
                return match_alt.group(1), match_alt.group(2)
                
    except Exception as e:
        print(f"Year/Month extraction error: {e}")
        
    return "2025", "3" # 見つからない場合のフォールバック

# --- 5. pdfファイル読込関数 ---
def pdf_reader(pdf_stream, target_staff):
    """PDFから場所名を抽出し、空白を完全除去して自分と他人のシフトを抽出"""
    # 検索対象の名前から空白を除去
    clean_target = re.sub(r'[\s　]', '', str(target_staff))
    
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
        
    # flavor='lattice' で罫線を解析
    tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    table_dictionary = {}
    
    for i, table in enumerate(tables):
        df = table.df
        if not df.empty:
            # --- 勤務地抽出ロジック ---
            text = str(df.iloc[0, 0])
            lines = text.splitlines()
            target_index = text.count('\n') // 2
            work_place = lines[target_index] if target_index < len(lines) else (lines[-1] if lines else "empty")
            df.iloc[0, 0] = work_place
            df = df.fillna('')

            # --- 検索用列の作成（スペース除去） ---
            search_col = df.iloc[:, 0].astype(str).str.replace(r'[\s　]', '', regex=True)

            # --- 抽出処理 ---
            matched_indices = df.index[search_col == clean_target].tolist()
        
            if matched_indices:
                idx = matched_indices[0]
                my_daily_shift = df.iloc[idx : idx+2].copy()
            
                # 2. 【変更】自分以外のデータ (other_daily_shift)
                # 自分を除外し、かつ表のヘッダー（0行目）も除外する
                other_daily_shift = df[(search_col != clean_target) & (df.index != 0)].copy()

                # 整形
                my_daily_shift = my_daily_shift.reset_index(drop=True)
                other_daily_shift = other_daily_shift.reset_index(drop=True)
                                        
                # 辞書に [自分, 他人] の形で格納
                table_dictionary[work_place] = [my_daily_shift, other_daily_shift]
        
    return table_dictionary

# --- 6. データ統合関数 ---
def data_integration(pdf_dic, time_schedule_dic):
    """
    PDFから読み取った場所ごとの表と、時程表を場所名(T2など)で紐付ける
    戻り値: {場所名: [自分のシフト, 他人のシフト, 時程表], ...}
    """
    integrated = {}
    for key in pdf_dic.items():
        if key in pdf_dic:
            # 自分のシフト(my_s), 他人のシフト(other_s)をpdf_dicから、時程表(t_s)をtime_dicから取得
            # ※pdf_dic[loc_key] が [my_s, other_s] のリストである前提
            my_s = pdf_dic[key][0]
            other_s = pdf_dic[key][1]
            t_s = time_schedule_dic[key]
            integrated[key] = [my_s, other_s, t_s]
    return integrated
