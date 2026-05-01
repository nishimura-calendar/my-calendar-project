import streamlit as st
import pandas as pd
import re
import unicodedata
import camelot
from googleapiclient.discovery import build
from google.oauth2 import service_account

# ==========================================
# 1. 認証サービス構築（app.py 6行目対応）
# ==========================================
def get_unified_services():
    """Google DriveおよびSheets APIサービスを構築"""
    if "gcp_service_account" in st.secrets:
        info = st.secrets["gcp_service_account"]
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=[
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/spreadsheets.readonly"
            ]
        )
        return build('drive', 'v3', credentials=creds), build('sheets', 'v4', credentials=creds)
    return None, None

# ==========================================
# 2. テキスト正規化・クレンジング
# ==========================================
def normalize_text(text):
    """空白除去、NFKC正規化、小文字化を行う"""
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def clean_key_from_pdf_val(val):
    """
    PDFの座標[0,0]から取得した値から、日付・曜日・時刻を除去。
    スプレッドシートのA列(Key)と照合可能な純粋な勤務地名にする。
    """
    text = str(val)
    # YYYY/MM/DD, MM/DD 形式の除去
    text = re.sub(r'\d{4}/\d{1,2}/\d{1,2}', '', text)
    text = re.sub(r'\d{1,2}/\d{1,2}', '', text)
    # (水) などの曜日、および時刻(00:00)の除去
    text = re.sub(r'\([月火水木金土日]\)', '', text)
    text = re.sub(r'\d{1,2}:\d{2}', '', text)
    return normalize_text(text)

# ==========================================
# 3. スプレッドシート行列範囲抽出ロジック
# ==========================================
def time_schedule_from_drive(sheets_service, file_id):
    """
    A列を行方向に検索してKeyを特定。
    D列以降を列方向に検索して行列範囲（時間軸）を切り出す。
    """
    spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=file_id).execute()
    sheets = spreadsheet.get('sheets', [])
    location_data_dic = {}

    for s in sheets:
        title = s.get("properties", {}).get("title")
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=file_id, range=f"'{title}'!A1:Z300").execute()
        vals = result.get('values', [])
        if not vals: continue

        df = pd.DataFrame(vals).fillna('')
        current_key = None
        start_row = 0
        
        # A列(0列目)を行方向に走査してKey(勤務地)を特定
        for i in range(len(df)):
            val_a = str(df.iloc[i, 0]).strip()
            if val_a != "":
                if current_key is not None:
                    # 前のKeyの行列範囲を確定させて辞書登録
                    location_data_dic[normalize_text(current_key)] = extract_col_range(df.iloc[start_row:i, :])
                current_key = val_a
                start_row = i
        
        # 最後のKey（勤務地）を登録
        if current_key is not None:
            location_data_dic[normalize_text(current_key)] = extract_col_range(df.iloc[start_row:, :])
                
    return location_data_dic

def extract_col_range(loc_df):
    """
    D列(3列目)以降を列方向に検索。
    数字が見つかってから、次に文字列が現れる直前までを有効な時間列とする。
    """
    if loc_df.empty: return loc_df
    sample_row = loc_df.iloc[0, :].tolist()
    
    col_start = 3 # デフォルト開始(D列)
    col_end = len(sample_row)
    
    # 最初に数字（時間に変換可能なもの）が見つかる位置
    for c in range(3, len(sample_row)):
        if re.match(r'^-?\d+(\.\d+)?$', str(sample_row[c])):
            col_start = c
            break
            
    # 数字が続いた後、最初に「数字以外の文字列」が見つかる位置
    for c in range(col_start, len(sample_row)):
        val = str(sample_row[c]).strip()
        if val != "" and not re.match(r'^-?\d+(\.\d+)?$', val):
            col_end = c
            break
            
    # A(勤務地), B(Key), C(ロッカー)列 ＋ 特定した時間軸列 を結合
    return pd.concat([loc_df.iloc[:, 0:3], loc_df.iloc[:, col_start:col_end]], axis=1)

# ==========================================
# 4. PDF座標指定・Key照合ロジック（基本事項の7）
# ==========================================
def pdf_reader_with_logic_7(pdf_stream, target_staff, time_dic):
    """
    PDFの座標[0,0], [0,1], [1,1]を使用して勤務地Keyを特定。
    スプレッドシートのKeyと一致する場合にのみ通過資格を認める。
    """
    clean_target = normalize_text(target_staff)
    # Streamlit上のファイルを一時保存
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    try:
        # 格子状の表(lattice)として読み込み
        tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    except Exception as e:
        st.error(f"Camelot解析失敗: {e}")
        return []

    final_results = []
    for table in tables:
        df = table.df
        if df.empty or len(df) < 2 or len(df.columns) < 2: continue
        
        # --- 座標による位置決め ---
        val_00 = df.iloc[0, 0] # 勤務地・日付等の混在セル
        val_01 = df.iloc[0, 1] # 補足情報
        val_11 = df.iloc[1, 1] # 補足情報
        
        # [0,0]から不要な文字を除去してKey(勤務地)を抽出
        pdf_key = clean_key_from_pdf_val(val_00)
        
        # スタッフ名の行を検索(0列目)
        search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
        if clean_target in search_col.values:
            idx = search_col[search_col == clean_target].index[0]
            # 自分(2行)のシフトデータを切り出し
            my_data = df.iloc[idx : idx + 2, :].copy()
            
            # --- 第三関門：通過資格（Key照合）の判断 ---
            matched_master_key = None
            if pdf_key in time_dic:
                matched_master_key = pdf_key
            else:
                # 表記揺れ対応（PDFが"T1(1)"でマスターが"T1"などの場合）
                matched_master_key = next((k for k in time_dic.keys() if k in pdf_key or pdf_key in k), None)
            
            # 合致するKeyが見つかった場合のみ、結果に追加
            if matched_master_key:
                final_results.append({
                    'key': matched_master_key,
                    'coords': {"[0,0]": val_00, "[0,1]": val_01, "[1,1]": val_11},
                    'my_data': my_data,
                    'time_range': time_dic[matched_master_key]
                })
                
    return final_results
