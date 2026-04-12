import pandas as pd
import pdfplumber
import camelot
import unicodedata
import re
import io
import calendar
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account

def get_gdrive_service(secrets):
    """Google Drive APIへのサービスオブジェクトを作成"""
    creds = service_account.Credentials.from_service_account_info(
        secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build('drive', 'v3', credentials=creds)

def time_schedule_from_drive(service, file_id):
    """
    【厳守】時程表（Excel形式）からブロックを抽出。
    「考察1.py」のロジックに基づき、列の境界を自動判定し、型エラーを防止する。
    """
    try:
        # ダウンロード処理
        file_metadata = service.files().get(fileId=file_id, fields='mimeType').execute()
        mime_type = file_metadata.get('mimeType')
        
        if mime_type == 'application/vnd.google-apps.spreadsheet':
            request = service.files().export_media(
                fileId=file_id,
                mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        else:
            request = service.files().get_media(fileId=file_id)
            
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        fh.seek(0)
        
        # Excelとして読み込み
        full_df = pd.read_excel(fh, header=None, engine='openpyxl', sheet_name=0)
        
        # --- 【考察1.py 準拠】列の境界（数値以外の文字列が現れる列）を自動判定 ---
        col_limit = len(full_df.columns)
        for i in range(3, len(full_df.columns)):
            val = full_df.iloc[0, i]
            if pd.isna(val) or val == "": continue
            try:
                float(val)
            except (ValueError, TypeError):
                col_limit = i
                break

        # 勤務地名の行（0列目が空でない行）を特定
        location_rows = full_df[full_df.iloc[:, 0].notna()].index.tolist()
        location_data_dic = {}
        
        for i, start_row in enumerate(location_rows):
            end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
            location_name = str(full_df.iloc[start_row, 0]).strip()
            
            # 判定された col_limit を使用して範囲を抽出
            data_range = full_df.iloc[start_row:end_row, 0:col_limit].copy().reset_index(drop=True)
            
            # 【重要】あらかじめ全データを object 型にキャスト（型エラー防止）
            data_range = data_range.astype(object)

            # --- 時間表記の変換処理 (例: 6.25 -> 6:15) ---
            for col in range(1, data_range.shape[1]):
                val = data_range.iloc[0, col]
                if pd.notna(val) and isinstance(val, (int, float)):
                    try:
                        hours = int(val)
                        minutes = int(round((val - hours) * 60))
                        data_range.iloc[0, col] = f"{hours}:{minutes:02d}"
                    except (ValueError, TypeError):
                        continue
                
            location_data_dic[location_name] = data_range.fillna('')
        
        return location_data_dic
    except Exception as e:
        raise e

def normalize_text(text):
    """比較用のテキスト正規化（空白完全除去）"""
    if not isinstance(text, str): return ""
    text = unicodedata.normalize('NFKC', text)
    return re.sub(r'[\s　]', '', text).lower()

def pdf_reader(pdf_stream, target_staff):
    """
    【厳守】PDFから指定スタッフの行と、それ以外のスタッフの行を抽出。
    「考察1.py」のcamelot/pdfplumber併用ロジックを反映。
    """
    clean_target = normalize_text(target_staff)
    # camelot用に一時保存
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    # camelotで格子状テーブルを解析
    try:
        tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    except Exception:
        # 万が一latticeで失敗した場合は、構造化データが取れないため空を返す
        return {}

    table_dictionary = {}
    
    for table in tables:
        df = table.df
        if not df.empty:
            # 勤務地（左上のセル内テキストの改行位置から推測）
            text = str(df.iloc[0, 0])
            lines = text.splitlines()
            target_idx = text.count('\n') // 2
            work_place = lines[target_idx] if target_idx < len(lines) else (lines[-1] if lines else "Unknown")
            
            df = df.fillna('')
            # 1列目の名前列をクレンジングして検索
            search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
            matched_indices = df.index[search_col == clean_target].tolist()
            
            if matched_indices:
                idx = matched_indices[0]
                # [自分の2行, 他人の全行(ヘッダーと自分を除く)]
                my_daily_shift = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
                other_daily_shift = df.drop([0, idx, idx+1] if idx+1 < len(df) else [0, idx]).copy().reset_index(drop=True)
                
                table_dictionary[work_place] = [my_daily_shift, other_daily_shift]
                
    return table_dictionary

def data_integration(pdf_dic, time_schedule_dic):
    """勤務地でPDFデータと時程表を統合する"""
    integrated_dic = {}
    logs = []
    
    for key, pdf_val in pdf_dic.items():
        # PDF側の場所名が、時程表側のキーに含まれているかチェック
        matched_key = None
        norm_key = normalize_text(key)
        for t_key in time_schedule_dic.keys():
            if norm_key in normalize_text(t_key):
                matched_key = t_key
                break
        
        if matched_key:
            # 統合形式: [自分DF, 他人DF, 時程表DF]
            integrated_dic[matched_key] = pdf_val + [time_schedule_dic[matched_key]]
            logs.append({"PDF側": key, "時程表側": matched_key, "Status": "OK"})
        else:
            logs.append({"PDF側": key, "時程表側": "---", "Status": "NotFound"})
            
    return integrated_dic, logs

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """1日分の詳細スケジュールを計算"""
    final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", key])
    
    # シフトコードに合致する時程を検索
    my_time_shift = time_schedule[time_schedule.iloc[:, 1].astype(str).str.strip() == str(shift_info).strip()]
    if my_time_shift.empty: return

    prev_val = ""
    # 3列目以降が時間枠
    for t_col in range(2, time_schedule.shape[1]):
        current_val = str(my_time_shift.iloc[0, t_col])
        if current_val.lower() == 'nan': current_val = ""

        if current_val != prev_val:
            if current_val != "":
                # 交代相手の特定
                mask = (time_schedule.iloc[:, t_col].astype(str) == current_val) & (time_schedule.iloc[:, 1] != shift_info)
                codes = time_schedule.loc[mask, time_schedule.columns[1]].tolist()
                
                names = []
                for code in codes:
                    if not str(code).strip(): continue
                    matches = other_staff_shift[other_staff_shift.iloc[:, col].astype(str).str.contains(str(code))]
                    names.extend([n.split('\n')[0].strip() for n in matches.iloc[:, 0].tolist() if n])
                
                u_names = "・".join(list(set(names)))
                subj = f"【{current_val}】from {u_names}" if u_names else f"【{current_val}】"
                start_t = str(time_schedule.iloc[0, t_col])
                final_rows.append([subj, target_date, start_t, target_date, "", "False", "", key])
            else:
                if final_rows and final_rows[-1][5] == "False":
                    final_rows[-1][4] = str(time_schedule.iloc[0, t_col])
        prev_val = current_val

def process_full_month(integrated_dic, year, month):
    """1ヶ月分ループ"""
    all_final_rows = []
    num_days = calendar.monthrange(year, month)[1]
    for day in range(1, num_days + 1):
        target_date_str = f"{year}-{month:02d}-{day:02d}"
        current_col = day + 1 
        for place_key, (my_row, others, time_sched) in integrated_dic.items():
            if current_col >= my_row.shape[1]: continue
            val = str(my_row.iloc[0, current_col])
            if not val or val.strip() == "" or val.lower() == 'nan': continue
            
            items = [i.strip() for i in re.split(r'[,、\s\n]+', val) if i.strip()]
            for item in items:
                shift_cal(place_key, target_date_str, current_col, item, my_row, others, time_sched, all_final_rows)
    return all_final_rows
