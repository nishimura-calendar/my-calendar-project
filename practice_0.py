import camelot
import pandas as pd
import pdfplumber
import re
import io

def pdf_reader(pdf_stream, target_staff):
    """PDFから場所名を抽出し、余分な空白や改行を除去して一致率を高める"""
    clean_target = str(target_staff).replace(' ', '').replace('　', '')
    
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
        
    tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    table_dictionary = {}
    
    for table in tables:
        df = table.df
        if not df.empty:
            # 1. セル内のテキストを取得
            text = str(df.iloc[0, 0])
            
            # 2. 改行で分割し、空行を除去したリストを作る
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            
            if lines:
                # 西村さんのロジック：中央付近の行に場所名があると想定
                target_idx = len(lines) // 2
                raw_place = lines[target_idx]
                
                # 3. 【重要】比較用に、全角・半角スペースと改行をすべて除去
                work_place = re.sub(r'[\s　]', '', raw_place)
            else:
                work_place = "Unknown"
            
            # --- デバッグ用：実際に読み取った加工後の名前を確認したい場合 ---
            # print(f"DEBUG: 読み取った場所名 -> {work_place}")

            df = df.fillna('')
            # 名前列（0列目）もスペースを除去して判定
            search_col = df.iloc[:, 0].astype(str).str.replace(r'[\s　]', '', regex=True)
            matched_indices = df.index[search_col == clean_target].tolist()
        
            if matched_indices:
                idx = matched_indices[0]
                my_daily_shift = df.iloc[idx : idx + 2, :].copy()
                other_daily_shift = df[(search_col != clean_target) & (df.index != 0)].copy()

                # 加工後の名前で辞書に格納
                table_dictionary[work_place] = [
                    my_daily_shift.reset_index(drop=True), 
                    other_daily_shift.reset_index(drop=True)
                ]
                
    return table_dictionary
    
def extract_year_month(pdf_stream):
    """PDFから年月を抽出"""
    with pdfplumber.open(pdf_stream) as pdf:
        text = "".join([page.extract_text() or "" for page in pdf.pages])
    match = re.search(r'(\d{4})\s*年\s*(\d{1,2})\s*月', text)
    if match: return match.group(1), match.group(2)
    return "2026", "3"

def time_schedule_from_drive(service, file_id):
    """GoogleドライブからExcel時程表を読み込み"""
    from googleapiclient.http import MediaIoBaseDownload
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done: _, done = downloader.next_chunk()
    fh.seek(0)
    
    full_df = pd.read_excel(fh, header=None, engine='openpyxl')
    # T2や本町などのキーワードで場所を特定（1列目に文字がある行）
    location_rows = full_df[full_df.iloc[:, 0].notna()].index.tolist()
    location_data_dic = {}
    
    for i, start_row in enumerate(location_rows):
        end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
        location_name = str(full_df.iloc[start_row, 0]).strip()
        data_range = full_df.iloc[start_row:end_row, 0:70].copy().reset_index(drop=True)

        # 時間表記変換
        for col in range(1, data_range.shape[1]):
            val = data_range.iloc[0, col]
            if pd.notna(val) and isinstance(val, (int, float)) and val > 0:
                total_min = int(round(val * 24 * 60))
                data_range.iloc[0, col] = f"{total_min // 60}:{total_min % 60:02d}"
                
        location_data_dic[location_name] = [data_range.fillna('')]
    return location_data_dic

def data_integration(pdf_dic, time_schedule_dic):
    """PDFと時程表を結合"""
    integrated_dic = {}
    for key, pdf_data in pdf_dic.items():
        if key in time_schedule_dic:
            integrated_dic[key] = pdf_data + time_schedule_dic[key]
    return integrated_dic

def working_hours(text):
    match = re.search(r'([①-⑳])', text)
    if not match: return "", ""
    parts = re.split(r'[①-⑳]', text)
    return parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""
