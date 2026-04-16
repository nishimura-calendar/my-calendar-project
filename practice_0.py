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

def normalize_text(text):
    """文字列の正規化"""
    if not text: return ""
    return unicodedata.normalize('NFKC', str(text)).replace(" ", "").replace("　", "").strip()

def extract_year_month_from_pdf(pdf_stream):
    """
    PDFの1ページ目から年月情報を抽出。
    例: '2024年 5月' や '2024 / 05' などの形式に対応。
    """
    try:
        pdf_stream.seek(0)
        with pdfplumber.open(pdf_stream) as pdf:
            first_page_text = pdf.pages[0].extract_text()
            if not first_page_text:
                return None, None
            
            # 年月のパターンマッチング
            match = re.search(r'(\d{4})\s*[年/]\s*(\d{1,2})\s*月?', first_page_text)
            if match:
                year = int(match.group(1))
                month = int(match.group(2))
                return year, month
    except Exception:
        pass
    return None, None

def time_schedule_from_drive(service, file_id):
    """スプレッドシートから勤務地ごとの時程表を抽出"""
    try:
        request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request); done = False
        while not done: _, done = downloader.next_chunk()
        fh.seek(0)
        full_df = pd.read_excel(fh, header=None, engine='openpyxl')
        
        location_rows = full_df[full_df.iloc[:, 0].notna()].index.tolist()
        location_data_dic = {}
        for i, start_row in enumerate(location_rows):
            end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
            location_name = str(full_df.iloc[start_row, 0]).strip()
            temp_range = full_df.iloc[start_row:end_row, :].copy()
            
            # 列の境界判定（3列目以降、数値以外の見出しが現れるまでをデータ範囲とする）
            current_col_limit = len(temp_range.columns)
            for col_idx in range(2, len(temp_range.columns)):
                val = temp_range.iloc[0, col_idx]
                if pd.isna(val): continue
                try: float(val)
                except: current_col_limit = col_idx; break
            
            data_range = temp_range.iloc[:, 0:current_col_limit].copy().reset_index(drop=True)
            # シリアル値形式の時間を HH:MM 形式に変換
            for col in range(1, data_range.shape[1]):
                t_val = data_range.iloc[0, col]
                if isinstance(t_val, (int, float)):
                    h = int(t_val * 24)
                    m = int(round((t_val * 24 - h) * 60))
                    data_range.iloc[0, col] = f"{h}:{m:02d}"
            
            location_data_dic[location_name] = data_range.fillna('')
        return location_data_dic
    except Exception as e: raise e

def pdf_reader(pdf_stream, target_staff):
    """PDFからCamelotを使用してスタッフのシフト行（2行分）を抽出"""
    clean_target = normalize_text(target_staff)
    pdf_stream.seek(0)
    # Camelotはファイルパスを必要とするため一時保存
    with open("temp.pdf", "wb") as f: f.write(pdf_stream.getbuffer())
    
    try:
        tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
        table_dic = {}
        for table in tables:
            df = table.df.replace(r'^\s*$', None, regex=True).fillna('')
            if df.empty: continue
            
            # 勤務地名の取得（0,0セルの改行位置から判定）
            loc_text = str(df.iloc[0, 0])
            loc_lines = loc_text.splitlines()
            work_place = loc_lines[len(loc_lines)//2] if loc_lines else "不明"
            
            search_col = df.iloc[:, 0].apply(normalize_text)
            # ターゲットスタッフの名前が含まれるインデックスを探す
            matches = df.index[search_col.str.contains(clean_target)].tolist()
            if matches:
                idx = matches[0]
                # 本人の行（通常2行セット）と、交代相手特定用の他者行を分離
                my_row = df.iloc[idx:idx+2, :].copy()
                others = df.drop([0, idx, idx+1] if idx+1 < len(df) else [0, idx]).copy()
                table_dic[work_place] = [my_row, others]
        return table_dic
    except: return {}

def data_integration(pdf_dic, time_schedule_dic):
    """PDFの勤務地と時程表の勤務地を紐付け"""
    integrated = {}; logs = []
    for p_loc, p_vals in pdf_dic.items():
        norm_p = normalize_text(p_loc)
        # 時程表側のキーに対して部分一致で検索
        m_key = next((k for k in time_schedule_dic.keys() if norm_p in normalize_text(k)), None)
        if m_key:
            integrated[m_key] = p_vals + [time_schedule_dic[m_key]]
            logs.append({"PDF側": p_loc, "時程表側": m_key, "結果": "OK"})
        else:
            logs.append({"PDF側": p_loc, "時程表側": "---", "結果": "未検出"})
    return integrated, logs

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """具体的スケジュール算定ロジック（交代相手の自動抽出を含む）"""
    # 終日予定としてシフト記号を登録
    final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", key])
    
    # シフト記号に一致する時程定義を取得
    shift_code = str(shift_info).strip()
    my_time_shift = time_schedule[time_schedule.iloc[:, 1].astype(str).str.strip() == shift_code]
    
    if my_time_shift.empty: return

    prev_val = ""
    for t_col in range(2, time_schedule.shape[1]):
        current_val = str(my_time_shift.iloc[0, t_col])
        if current_val.lower() == 'nan': current_val = ""
        
        if current_val != prev_val:
            if current_val != "":
                # 交代相手の特定
                mask = (time_schedule.iloc[:, t_col].astype(str) == current_val) & (time_schedule.iloc[:, 1] != shift_code)
                codes = time_schedule.loc[mask, time_schedule.columns[1]].tolist()
                
                names = []
                for code in codes:
                    if not str(code).strip(): continue
                    # 他のスタッフの当日列にそのコードが含まれているかチェック
                    matches = other_staff_shift[other_staff_shift.iloc[:, col].astype(str).str.contains(str(code))]
                    names.extend([n.split('\n')[0].strip() for n in matches.iloc[:, 0].tolist() if n])
                
                u_names = "・".join(list(set(names)))
                subj = f"【{current_val}】from {u_names}" if u_names else f"【{current_val}】"
                start_t = str(time_schedule.iloc[0, t_col])
                final_rows.append([subj, target_date, start_t, target_date, "", "False", "", key])
            else:
                # 予定の終了時刻を設定
                if final_rows and final_rows[-1][5] == "False":
                    final_rows[-1][4] = str(time_schedule.iloc[0, t_col])
        prev_val = current_val

def process_full_month(integrated_dic, year, month):
    """月間の全日程をループ処理して最終データを生成"""
    final_results = []
    num_days = calendar.monthrange(year, month)[1]
    
    for day in range(1, num_days + 1):
        target_date = f"{year}/{month:02d}/{day:02d}"
        for key, (my_row, others, time_sched) in integrated_dic.items():
            # PDFの日付列を判定（通常 day+1 列目などだが表構造に依存）
            # ここではシンプルに day+1 列目を参照する例
            col_idx = day + 1 
            if col_idx >= my_row.shape[1]: continue
            
            # 2行セットのうち、1行目にシフト記号、2行目に詳細がある構造を想定
            cell_val = str(my_row.iloc[0, col_idx]).split('\n')
            shift_info = cell_val[0].strip()
            
            if shift_info and not any(x in shift_info for x in ["休", "有休", "nan", " "]):
                shift_cal(key, target_date, col_idx, shift_info, my_row, others, time_sched, final_results)
                
    return final_results
