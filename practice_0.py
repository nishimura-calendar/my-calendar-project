import camelot
import pandas as pd
import pdfplumber
import re
import io
import numpy as np

def pdf_reader(pdf_stream, target_staff):
    """
    PDFから2段構造（上段：記号、下段：時間）を考慮して、
    自分(TARGET_STAFF)のシフトと、他人のシフトを抽出する。
    """
    # スタッフ名から空白を除去
    clean_target = re.sub(r'[\s　]', '', str(target_staff))
    
    # Camelot用に一時ファイルを作成
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
        
    # PDFの全ページから表を抽出
    tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    table_dictionary = {}
    
    for table in tables:
        df = table.df
        if df.empty:
            continue
            
        # 1. 勤務地名の取得（A1セルの改行中央付近から抽出）
        text = str(df.iloc[0, 0])
        lines = text.splitlines()
        target_index = text.count('\n') // 2
        work_place = lines[target_index] if target_index < len(lines) else (lines[-1] if lines else "unknown")
        
        # 2. 検索用列（A列の名前から空白を除去）
        search_col = df.iloc[:, 0].astype(str).str.replace(r'[\s　]', '', regex=True)
        matched_indices = df.index[search_col == clean_target].tolist()
        
        if matched_indices:
            idx = matched_indices[0]
            
            # --- 自分のデータ抽出（2段セット構造） ---
            # 自分が最終行の場合は1行のみ、そうでなければ下の行を含めて2行取得
            if idx + 1 < len(df):
                my_daily_shift = df.iloc[idx : idx+2, :].copy()
            else:
                # 最終行の場合、構造を合わせるためダミーの空行を追加
                my_daily_shift = df.iloc[idx : idx+1, :].copy()
                empty_row = pd.DataFrame([[''] * df.shape[1]], columns=df.columns)
                my_daily_shift = pd.concat([my_daily_shift, empty_row], ignore_index=True)
            
            # --- 他人のデータ抽出（引き継ぎ相手解析用） ---
            # 自分の2行とヘッダー(0)を除外し、かつ「名前が入っている行」だけを抽出（時間行を除外）
            exclude_idx = [0, idx, idx + 1]
            other_daily_shift = df[~df.index.isin(exclude_idx)].copy()
            # A列（名前列）が空でない行のみを「スタッフ行」として認識
            other_daily_shift = other_daily_shift[other_daily_shift.iloc[:, 0].str.strip() != ""].copy()

            # インデックスの初期化
            my_daily_shift = my_daily_shift.reset_index(drop=True)
            other_daily_shift = other_daily_shift.reset_index(drop=True)
            
            table_dictionary[work_place] = [my_daily_shift, other_daily_shift]
            
    return table_dictionary

def extract_year_month(pdf_stream):
    """PDFのテキストから『2026年3月度』のような記述を探し、年と月を返す"""
    pdf_stream.seek(0)
    with pdfplumber.open(pdf_stream) as pdf:
        text = pdf.pages[0].extract_text()
        if text:
            match = re.search(r'(\d{4})年\s*(\d{1,2})月', text)
            if match:
                return match.group(1), match.group(2)
    return "2026", "3" # 見つからない場合のデフォルト

def time_schedule_from_drive(service, file_id):
    """
    Google Driveから時程表(Excel)を取得。
    時刻列の終わりを自動判定し、シリアル値を時刻形式に変換して抽出する。
    """
    from googleapiclient.http import MediaIoBaseDownload
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    
    # Excelファイルを読み込み（全シート）
    excel_data = pd.read_excel(fh, sheet_name=None, header=None, engine='openpyxl')
    location_data_dic = {}
    
    for sheet_name, full_df in excel_data.items():
        if full_df.empty:
            continue

        # --- 【境界判定】3列目以降をループし、時刻（数値）が終わる列（col_limit）を探す ---
        col_limit = len(full_df.columns)
        for i in range(2, len(full_df.columns)): # 3列目(index 2)から
            val = full_df.iloc[0, i]
            # 空白、または数値に変換できない値が出たらそこを境界とする
            if pd.isna(val) or val == "":
                col_limit = i
                break
            try:
                float(val)
            except (ValueError, TypeError):
                col_limit = i
                break

        # A列が空でない行（勤務地名が入っている行）を特定
        location_rows = full_df[full_df.iloc[:, 0].astype(str).str.strip() != ""].index.tolist()
        
        for i, start_row in enumerate(location_rows):
            # 次の勤務地行、またはシートの末尾までを範囲とする
            end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
            
            # 勤務地名を取得
            location_name = str(full_df.iloc[start_row, 0]).strip()
            
            # 判定された col_limit までの範囲を抽出
            data_range = full_df.iloc[start_row:end_row, 0:col_limit].copy()
            data_range = data_range.reset_index(drop=True).astype(object)

            # --- 時間表記の変換 (Excelシリアル値 -> HH:MM) ---
            for col in range(2, data_range.shape[1]):
                val = data_range.iloc[0, col]
                if pd.notna(val) and isinstance(val, (int, float)):
                    try:
                        # 0.375 のようなシリアル値を時間に変換
                        hours = int(val * 24) if val < 1 else int(val)
                        minutes = int(round((val * 24 - hours) * 60)) if val < 1 else 0
                        data_range.iloc[0, col] = f"{hours}:{minutes:02d}"
                    except:
                        continue
                
            # 欠損値を空文字に
            data_range = data_range.fillna('')
            location_data_dic[location_name] = [data_range]
            
    return location_data_dic

def data_integration(pdf_dic, time_sched_dic):
    """場所名をキーにして、PDFデータと時程表データを統合する"""
    integrated = {}
    # 時程表側のキーから空白を除去したマップを作成
    clean_time_keys = {re.sub(r'[\s　]', '', k): (k, v) for k, v in time_sched_dic.items()}
    
    for pk, pv in pdf_dic.items():
        cpk = re.sub(r'[\s　]', '', pk) # PDF側の場所名から空白除去
        if cpk in clean_time_keys:
            orig_k, tv = clean_time_keys[cpk]
            # [自分の2行, 他人の行リスト, 時程表データ] のリストにする
            integrated[pk] = pv + tv
            
    return integrated
