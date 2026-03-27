import pandas as pd
import io
import re
import pdfplumber
from googleapiclient.http import MediaIoBaseDownload

# --- 1. 時間整形関数：数値やシリアル値を「HH:MM」の文字列に変換 ---
def format_to_hhmm(val):
    try:
        if val == "" or str(val).lower() == "nan": 
            return ""
        num = float(val)
        # 1未満ならシリアル値、1以上なら時刻数値として計算
        h = int(num * 24 if num < 1 else num)
        m = int(round((num * 24 - h) * 60 if num < 1 else (num - h) * 60))
        return f"{h:02d}:{m:02d}"
    except:
        return str(val).strip()

# --- 2. 本町専用：2段目(v2)から「開始@終了」を抜き出す ---
def parse_special_shift(text):
    if not text or str(text).lower() == 'nan' or text == "":
        return "", "", False
    
    # 正規表現で「数字 @ 数字」のパターンを探す
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
        # 全列(3列目以降)の時間軸(1行目)をHH:MMに一括変換
        for col in range(2, df.shape[1]):
            df.iloc[0, col] = format_to_hhmm(df.iloc[0, col])
        location_data_dic[loc_name] = df
    return location_data_dic

# --- 4. 年月抽出関数 ---
def extract_year_month(pdf_stream):
    with pdfplumber.open(pdf_stream) as pdf:
        text = pdf.pages[0].extract_text()
        match = re.search(r'(\d{4})年\s*(\d{1,2})月', text)
        if match:
            return int(match.group(1)), int(match.group(2))
    return None, None

# --- 5. データ統合関数 ---
def data_integration(pdf_dic, time_schedule_dic):
    integrated = {}
    for loc_key in pdf_dic.keys():
        if loc_key in time_schedule_dic:
            my_s = pdf_dic[loc_key][0]
            other_s = pdf_dic[loc_key][1]
            t_s = time_schedule_dic[loc_key]
            integrated[loc_key] = [my_s, other_s, t_s]
    return integrated

# --- 6. PDF読み取り関数 ---
def pdf_reader(file):
    with pdfplumber.open(file) as pdf:
        all_tables = []
        for page in pdf.pages:
            table = page.extract_table()
            if table:
                all_tables.append(pd.DataFrame(table))
    return all_tables
