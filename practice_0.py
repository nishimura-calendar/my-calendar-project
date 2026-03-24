import pandas as pd
import re
import io

def time_schedule_from_drive(service, file_id):
    """Google Driveから時程表(Excel)を取得し、時刻列の終わりを自動判定して抽出"""
    from googleapiclient.http import MediaIoBaseDownload
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    
    # 全シートを読み込み
    excel_data = pd.read_excel(fh, sheet_name=None, header=None, engine='openpyxl')
    location_data_dic = {}
    
    for sheet_name, full_df in excel_data.items():
        if full_df.empty:
            continue

        # --- 【境界判定】3列目以降をループし、時刻（数値）が終わる列を探す ---
        col_limit = len(full_df.columns)
        for i in range(2, len(full_df.columns)): # index 2(3列目)から開始
            val = full_df.iloc[0, i]
            # 空白、または数値に変換できない文字列（「出勤」など）が出たら終了
            if pd.isna(val) or val == "":
                col_limit = i
                break
            try:
                float(val)
            except (ValueError, TypeError):
                col_limit = i
                break

        # A列が空でない行を「場所」の開始位置とする
        # 文字列以外のゴミを除去するため、str.strip() して判定
        location_rows = full_df[full_df.iloc[:, 0].astype(str).str.strip() != ""].index.tolist()
        
        for i, start_row in enumerate(location_rows):
            # 次の勤務地行、またはファイルの最後までを抽出範囲とする
            end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
            
            # 勤務地名（A列）を取得
            location_name = str(full_df.iloc[start_row, 0]).strip()
            
            # 判定された col_limit を使用して、必要な列範囲だけを抽出
            data_range = full_df.iloc[start_row:end_row, 0:col_limit].copy()
            
            # インデックスと全データを整形
            data_range = data_range.reset_index(drop=True).astype(object)

            # --- 時間表記の変換 (0.375 -> 9:00 など) ---
            for col in range(2, data_range.shape[1]): # 時刻は3列目以降
                val = data_range.iloc[0, col]
                if pd.notna(val) and isinstance(val, (int, float)):
                    try:
                        hours = int(val * 24) if val < 1 else int(val) # Excelシリアル値対応
                        minutes = int(round((val * 24 - hours) * 60)) if val < 1 else 0
                        data_range.iloc[0, col] = f"{hours}:{minutes:02d}"
                    except:
                        continue
                
            # 欠損値を空白に変換
            data_range = data_range.fillna('')
            
            # 辞書に追加
            location_data_dic[location_name] = [data_range]
            
    return location_data_dic
