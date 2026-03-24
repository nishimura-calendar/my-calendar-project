import camelot
import pandas as pd
import pdfplumber
import re
import io
import numpy as np

def pdf_reader(pdf_stream, target_staff):
    # Pythonの正規表現ライブラリ re を使用して、変数 target_staff に含まれる すべての空白文字（半角スペース、全角スペース、タブ、改行など）を完全に削除 する処理
    clean_target = re.sub(r'[\s　]', '', str(target_staff))
    
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
        
    tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    table_dictionary = {}
    
    for i, table in enumerate(tables):
        df = table.df
        if not df.empty:
            text = str(df.iloc[0, 0])
            lines = text.splitlines()
            target_index = text.count('\n') // 2
            work_place = lines[target_index] if target_index < len(lines) else (lines[-1] if lines else "empty")
            df.iloc[0, 0] = work_place
            df = df.fillna('')

            # 検索用列の作成（全角半角スペース除去）
            search_col = df.iloc[:, 0].astype(str).apply(lambda x: re.sub(r'[\s　]', '', x))

            matched_indices = df.index[search_col == clean_target].tolist()
        
            if matched_indices:
                idx = matched_indices[0]
                last_idx = df.index[-1]
                            
                if idx == last_idx:
                    my_daily_shift = df.iloc[idx : idx+1].copy()
                else:
                    my_daily_shift = df.iloc[idx : idx+2].copy()
            
                # 自分を除外し、かつ表のヘッダーも除外
                other_daily_shift = df[(search_col != clean_target) & (df.index != 0)].copy()

                my_daily_shift = my_daily_shift.reset_index(drop=True)
                other_daily_shift = other_daily_shift.reset_index(drop=True)
                                        
                table_dictionary[work_place] = [my_daily_shift, other_daily_shift]
        
    return table_dictionary

def extract_year_month(pdf_stream):
    """PDFから年月を抽出"""
    with pdfplumber.open(pdf_stream) as pdf:
        text = "".join([page.extract_text() or "" for page in pdf.pages])
    match = re.search(r'(\d{4})\s*年\s*(\d{1,2})\s*月', text)
    if match: return match.group(1), match.group(2)
    return "年月不明"

def time_schedule_from_drive(service, file_id):
    """GoogleドライブからExcel時程表を読み込み、場所名の空白を除去"""
    from googleapiclient.http import MediaIoBaseDownload
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done: _, done = downloader.next_chunk()
    fh.seek(0)
    
    full_df = pd.read_excel(fh, header=None, engine='openpyxl')
    
    # --- 【新規追加】列の境界（文字列が現れる列）を自動判定 ---
    # 3列目以降をループし、数値に変換できない文字列が出たらそこを境界とする
    col_limit = len(full_df.columns)
    for i in range(3, len(full_df.columns)):
        val = full_df.iloc[0, i]
        try:
            # 数値（時刻）として解釈できるか試行
            float(val)
        except (ValueError, TypeError):
            # 数値に変換できない＝「出勤」などの文字列に到達したと判断
            col_limit = i
            break
            
    # A列が空でない行を場所の開始位置とする
    location_rows = full_df[full_df.iloc[:, 0].notna()].index.tolist()
    location_data_dic = {}
    
    # 3. 各勤務地行を反復処理し、データを抽出する
    for i, start_row in enumerate(location_rows):
        
        # 次の勤務地行のインデックスを取得 (最後の勤務地の場合はファイルの最後まで)
        end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
        
        # 勤務地名を取得
        location_name = full_df.iloc[start_row, 0]
        
        # --- 【修正箇所】判定された col_limit を使用して範囲を抽出 ---
        data_range = full_df.iloc[start_row:end_row, 0:col_limit].copy()
        
        # インデックスを0から振り直す
        data_range = data_range.reset_index(drop=True)

        # あらかじめ全データを object 型にキャスト（警告防止）
        data_range = data_range.astype(object)

        # --- 時間表記の変換処理 ---
        for col in range(1, data_range.shape[1]):
            val = data_range.iloc[0, col]
            
            if pd.notna(val) and isinstance(val, (int, float)):
                try:
                    hours = int(val)
                    minutes = int(round((val - hours) * 60))
                    data_range.iloc[0, col] = f"{hours}:{minutes:02d}"
                except (ValueError, TypeError):
                    continue
                
        # 欠損値を空白に変換
        data_range = data_range.fillna('')
        
        # 辞書に追加
        location_data_dic[location_name] = [data_range]
        
    return location_data_dic

def data_integration(pdf_dic, time_schedule_dic):
    """PDFと時程表を、空白を無視した場所名で紐付け"""
    integrated_dic = {}
    
    # 比較用に時程表のキーから空白を除去した辞書を作成
    clean_time_sched = {re.sub(r'[\s　]', '', k): (k, v) for k, v in time_schedule_dic.items()}
    
    for pdf_key, pdf_data in pdf_dic.items():
        # PDF側のキーからも空白を除去
        clean_pdf_key = re.sub(r'[\s　]', '', pdf_key)
        
        if clean_pdf_key in clean_time_sched:
            original_key, time_data = clean_time_sched[clean_pdf_key]
            # [自分のシフト, 他人のシフト, Excelのデータ]
            integrated_dic[pdf_key] = pdf_data + time_data
            
    return integrated_dic
