import camelot
import pandas as pd
import pdfplumber
import re
import io
import datetime

def pdf_reader(pdf_stream, target_staff):
    """PDFからスタッフの勤務行とそれ以外のスタッフ行を抽出する"""
    clean_target = str(target_staff).replace(' ', '').replace('　', '')
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    table_dictionary = {}
    
    for table in tables:
        df = table.df
        if not df.empty:
            text = str(df.iloc[0, 0])
            lines = text.splitlines()
            target_idx = text.count('\n') // 2
            work_place = lines[target_idx] if target_idx < len(lines) else (lines[-1] if lines else "Unknown")
            
            df = df.fillna('')
            search_col = df.iloc[:, 0].astype(str).str.replace(r'[\s　]', '', regex=True)
            matched_indices = df.index[search_col == clean_target].tolist()
            
            if matched_indices:
                idx = matched_indices[0]
                table_dictionary[work_place] = [df.iloc[idx : idx + 2, :].copy(), df.drop([0, idx, idx+1]).copy()]
    return table_dictionary

def extract_year_month(pdf_stream):
    """PDFから年月を抽出する"""
    with pdfplumber.open(pdf_stream) as pdf:
        text = "".join([page.extract_text() or "" for page in pdf.pages])
    match = re.search(r'(\d{4})\s*年\s*(\d{1,2})\s*月', text)
    return (match.group(1), match.group(2)) if match else ("2026", "3")

def time_schedule_from_drive(service, file_id):
    """Google Driveから時程表を読み込み、時刻軸をクレンジングする"""
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
            
    # 2. 勤務地名の行を特定する
    # 0列目 (インデックス0) でNaNではない行が勤務地（ブロックの開始）行
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
    """勤務地でPDFデータと時程表を統合する"""
    integrated_dic = {}
    for key, pdf_val in pdf_dic.items():
        if key in time_schedule_dic:
            integrated_dic[key] = pdf_val + time_schedule_dic[key]
    return integrated_dic
