import camelot
import pandas as pd
import pdfplumber
import re
import io

def pdf_reader(pdf_stream, target_staff):
    """PDFから場所名を抽出し、空白を完全除去して照合精度を高める"""
    # 検索対象の名前も空白を除去
    clean_target = re.sub(r'[\s　]', '', str(target_staff))
    
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
        
    tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    table_dictionary = {}
    
    for table in tables:
        df = table.df
        if not df.empty:
            # 1. A1セルのテキストを取得し、改行で分割（空行は無視）
            text = str(df.iloc[0, 0])
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            
            if lines:
                # 2. 中央付近の行を場所名として取得
                target_idx = len(lines) // 2
                raw_place = lines[target_idx]
                # 3. 【重要】場所名から全角・半角スペース、改行をすべて除去
                work_place = re.sub(r'[\s　]', '', raw_place)
            else:
                work_place = "Unknown"

            df = df.fillna('')
            # 4. 0列目（名前列）からも空白を除去して一致判定
            search_col = df.iloc[:, 0].astype(str).str.replace(r'[\s　]', '', regex=True)
            matched_indices = df.index[search_col == clean_target].tolist()
        
            if matched_indices:
                idx = matched_indices[0]
                my_daily_shift = df.iloc[idx : idx + 2, :].copy()
                other_daily_shift = df[(search_col != clean_target) & (df.index != 0)].copy()

                # 余計な空白がない「純粋な場所名」をキーにして格納
                table_dictionary[work_place] = [
                    my_daily_shift.reset_index(drop=True), 
                    other_daily_shift.reset_index(drop=True)
                ]
                
    return table_dictionary

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
    location_rows = full_df[full_df.iloc[:, 0].notna()].index.tolist()
    location_data_dic = {}
    
    for i, start_row in enumerate(location_rows):
        end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
        # Excel側の場所名からも空白を完全に除去する
        raw_name = str(full_df.iloc[start_row, 0])
        location_name = re.sub(r'[\s　]', '', raw_name)
        
        data_range = full_df.iloc[start_row:end_row, 0:70].copy().reset_index(drop=True)
        # (時間変換ロジックはそのまま)
        for col in range(1, data_range.shape[1]):
            val = data_range.iloc[0, col]
            if pd.notna(val) and isinstance(val, (int, float)) and val > 0:
                total_min = int(round(val * 24 * 60))
                data_range.iloc[0, col] = f"{total_min // 60}:{total_min % 60:02d}"
                
        location_data_dic[location_name] = [data_range.fillna('')]
    return location_data_dic

# その他の関数は変更なし
