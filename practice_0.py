import pandas as pd
import re
import unicodedata
import camelot

def normalize_text(text):
    """テキスト正規化（空白・全角半角の統一）"""
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def clean_key_from_pdf_val(val):
    """
    指定座標から取得した文字列を洗浄。
    日付・曜日・時刻等を除去し、純粋な勤務地名(Key)を抽出。
    """
    text = str(val)
    # 日付(2026/04/01等)、曜日((水)等)、時刻(14:00等)を除去
    text = re.sub(r'\d{4}/\d{1,2}/\d{1,2}', '', text)
    text = re.sub(r'\([月火水木金土日]\)', '', text)
    text = re.sub(r'\d{1,2}:\d{2}', '', text)
    return normalize_text(text)

def time_schedule_from_drive(sheets_service, file_id):
    """
    【スプレッドシート解析ロジック】
    A列を行方向に走査し、次の勤務地が出るまでを一つのKeyの範囲とする。
    D列以降で数値〜文字列までの範囲を特定し、Key(勤務地)を辞書登録する。
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
        
        for i in range(len(df)):
            val_a = str(df.iloc[i, 0]).strip()
            if val_a != "":
                if current_key is not None:
                    # 前のKeyの行列範囲を確定
                    location_data_dic[normalize_text(current_key)] = extract_col_range(df.iloc[start_row:i, :])
                current_key = val_a
                start_row = i
        
        # 最後のKeyを登録
        if current_key is not None:
            location_data_dic[normalize_text(current_key)] = extract_col_range(df.iloc[start_row:, :])
                
    return location_data_dic

def extract_col_range(loc_df):
    """【列範囲特定】D列以降で数値から始まり、文字列が現れる直前までを切り出す"""
    sample_row = loc_df.iloc[0, :].tolist()
    col_start = 3
    col_end = len(sample_row)
    for c in range(3, len(sample_row)):
        if re.match(r'^-?\d+(\.\d+)?$', str(sample_row[c])):
            col_start = c
            break
    for c in range(col_start, len(sample_row)):
        val = str(sample_row[c]).strip()
        if val != "" and not re.match(r'^-?\d+(\.\d+)?$', val):
            col_end = c
            break
    # A,B,C列 + 特定した時間列
    return pd.concat([loc_df.iloc[:, 0:3], loc_df.iloc[:, col_start:col_end]], axis=1)

def pdf_reader_with_logic_7(pdf_stream, target_staff, time_dic):
    """
    【基本事項の7：最終判定ロジック】
    座標[0,0], [0,1], [1,1]から情報を特定し、通過資格（Key照合）を判断する。
    """
    clean_target = normalize_text(target_staff)
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    try:
        tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    except: return []

    final_results = []
    for table in tables:
        df = table.df
        if df.empty or len(df) < 2 or len(df.columns) < 2: continue
        
        # 座標設定による位置決め
        val_00 = df.iloc[0, 0] # 勤務地Key候補
        val_01 = df.iloc[0, 1] # 補足情報1
        val_11 = df.iloc[1, 1] # 補足情報2
        
        # [0,0]からKeyを抽出・洗浄
        pdf_key = clean_key_from_pdf_val(val_00)
        
        # スタッフ名行を検索
        search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
        if clean_target in search_col.values:
            idx = search_col[search_col == clean_target].index[0]
            my_data = df.iloc[idx : idx + 2, :].copy()
            
            # 第三関門：PDFの座標から得たKeyが時程表マスターに存在するか
            matched_master_key = None
            if pdf_key in time_dic:
                matched_master_key = pdf_key
            else:
                # 曖昧一致（PDF側の表記揺れ対応）
                matched_master_key = next((k for k in time_dic.keys() if k in pdf_key or pdf_key in k), None)
            
            # 通過資格ありと判断された場合のみ結果に追加
            if matched_master_key:
                final_results.append({
                    'key': matched_master_key,
                    'coords': {"[0,0]": val_00, "[0,1]": val_01, "[1,1]": val_11},
                    'my_data': my_data,
                    'time_range': time_dic[matched_master_key]
                })
                
    return final_results
