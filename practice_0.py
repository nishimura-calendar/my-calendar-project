import pandas as pd
import camelot
import unicodedata
import re
import io
import calendar
import streamlit as st
from googleapiclient.http import MediaIoBaseDownload

# --- 1. テキストの正規化 ---
def normalize_text(text):
    if not isinstance(text, str): return ""
    # 空白、全角スペースを除去し、NFKC正規化後に小文字化
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def find_name_and_index_in_cell(target_name, cell_text):
    """
    【4/20 打ち合わせ準拠】
    セル内を改行で分割し、ターゲット名が含まれる要素のインデックス(offset)を返す。
    これにより、同じセル内の複数行から「自分のデータ」を正確に特定する。
    """
    if not cell_text: return False, 0
    clean_target = normalize_text(target_name)
    if not clean_target: return False, 0
    
    lines = str(cell_text).split('\n')
    for idx, line in enumerate(lines):
        clean_line = normalize_text(line)
        if clean_target in clean_line or clean_line in clean_target:
            return True, idx
    return False, 0

# --- 2. 時程表の取得 (consideration_0.py 準拠の動的解析) ---
def time_schedule_from_drive(service, file_id):
    """
    時程表スプレッドシートを解析し、A列にある勤務地名をキーにして保持。
    """
    try:
        file_metadata = service.files().get(fileId=file_id, fields='mimeType').execute()
        request = service.files().get_media(fileId=file_id)
        if file_metadata.get('mimeType') == 'application/vnd.google-apps.spreadsheet':
            request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done: _, done = downloader.next_chunk()
        fh.seek(0)
        
        # すべて文字列として読み込む
        full_df = pd.read_excel(fh, header=None, engine='openpyxl', sheet_name=0, dtype=str)
        
        # A列に値がある行を各勤務地のデータ開始行とする
        location_rows = full_df[full_df.iloc[:, 0].notna()].index.tolist()
        location_data_dic = {}
        
        for i, start_row in enumerate(location_rows):
            end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
            location_name = str(full_df.iloc[start_row, 0]).strip()
            temp_range = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
            
            # 時間列の動的特定ロジック
            time_row = temp_range.iloc[0, :]
            first_num_col = None
            last_num_col = None
            
            for col_idx, val in enumerate(time_row):
                if col_idx < 1: continue # A列は飛ばす
                try:
                    float(val)
                    if first_num_col is None: first_num_col = col_idx
                    last_num_col = col_idx
                except: continue
            
            if first_num_col is not None:
                start_col = max(1, first_num_col - 1) # 数値開始の1つ前から抽出
                end_col = last_num_col + 1
                target_cols = [0, 1] + list(range(start_col, end_col))
                temp_range = temp_range.iloc[:, target_cols].copy()
                
                # 数値(6.25)を時刻(6:15)形式に変換
                for col in range(len(temp_range.columns)):
                    if col < 2: continue
                    v = temp_range.iloc[0, col]
                    try:
                        f_v = float(v)
                        h = int(f_v)
                        m = int(round((f_v - h) * 60))
                        temp_range.iloc[0, col] = f"{h}:{m:02d}"
                    except: pass
            
            location_data_dic[location_name] = temp_range.fillna('')
            
        return location_data_dic
    except Exception as e:
        st.error(f"時程表取得エラー: {e}")
        return {}

# --- 3. PDF解析 (consideration_0.py の勤務地抽出ロジック完全再現) ---
def pdf_reader(pdf_stream, target_staff, file_name=""):
    pdf_stream.seek(0)
    year, month = None, None
    # ファイル名から年月を推定
    nums = re.findall(r'\d+', normalize_text(file_name))
    for n in nums:
        if len(n) == 4: year = int(n)
        if len(n) <= 2: month = int(n)

    temp_path = "temp_process.pdf"
    with open(temp_path, "wb") as f: f.write(pdf_stream.getbuffer())
    
    pdf_results = {}
    
    # Camelotでテーブル抽出
    for flavor in ['lattice', 'stream']:
        try:
            tables = camelot.read_pdf(temp_path, pages='all', flavor=flavor)
        except: continue
        
        for table in tables:
            df = table.df
            if df.empty: continue
            
            # 【重要】A1セルから勤務地名を抽出
            header_lines = str(df.iloc[0, 0]).splitlines()
            work_place = header_lines[len(header_lines)//2] if header_lines else "Unknown"
            work_place = work_place.strip()

            for i in range(len(df)):
                cell_val = str(df.iloc[i, 0])
                # 4/20 打ち合わせに基づきオフセット(行位置)を取得
                found, offset = find_name_and_index_in_cell(target_staff, cell_val)
                
                if found:
                    # 自分のシフト（2行分）
                    my_daily = df.iloc[i : i + 2, :].copy().reset_index(drop=True)
                    # 交代相手検索用の全データ
                    others = df.copy().reset_index(drop=True)
                    
                    # オフセット情報をセル内に一時保存
                    my_daily.iloc[0, 0] = f"{target_staff}_offset_{offset}"
                    
                    # 勤務地(work_place)をキーとして結果を保持
                    pdf_results[work_place] = [my_daily, others]
                    break
        if pdf_results: break # 1つ見つかれば終了
                    
    return pdf_results, year, month

# --- 4. データの紐付けと警告表示 ---
def integrate_with_warning(pdf_results, time_dic):
    """
    勤務地名をキーにしてPDFデータと時程表を紐付ける。
    存在しない場合は警告を表示。
    """
    integrated = {}
    for wp_key in pdf_results:
        if wp_key not in time_dic:
            st.error(f"{wp_key}という勤務地は登録されていません確認してください。")
            continue
        
        # 統合データ: [自分のシフト, 全員のデータ, 対応する時程表]
        integrated[wp_key] = [pdf_results[wp_key][0], pdf_results[wp_key][1], time_dic[wp_key]]
    
    return integrated

# --- 5. 月間スケジュール生成 ---
def process_full_month(integrated_dic, year, month):
    final_rows = [["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location"]]
    if not year or not month: return final_rows
    
    _, last_day = calendar.monthrange(year, month)
    
    for day in range(1, last_day + 1):
        target_date = f"{year}/{month:02d}/{day:02d}"
        for place_key, data in integrated_dic.items():
            my_daily, others, time_sched = data[0], data[1], data[2]
            
            # メタデータからオフセットを取得
            meta = str(my_daily.iloc[0, 0])
            offset = int(meta.split("_offset_")[-1]) if "_offset_" in meta else 0
            
            # 日付列（A列が0なので、日付nはn列目に対応すると仮定）
            if day >= my_daily.shape[1]: continue
            
            raw_val = str(my_daily.iloc[0, day])
            val_lines = raw_val.split('\n')
            # 自分の行(offset)からシフト記号を取得
            shift_text = val_lines[offset].strip() if offset < len(val_lines) else raw_val

            # シフト記号（A, B, C... または 休暇）の抽出
            shifts = re.findall(r'[A-Z\d]+|[公有休特欠]', shift_text)
            for s_info in shifts:
                if any(k in s_info for k in ["公", "有", "休", "特", "欠"]):
                    final_rows.append([f"【{s_info}】", target_date, "", target_date, "", "True", "休暇", place_key])
                else:
                    # 詳細計算の呼び出し（consideration.py のロジックを流用）
                    # ※ここでの引数 col は PDF上の日付列インデックス
                    import consideration as cons
                    cons.shift_cal(place_key, target_date, day, s_info, my_daily, others, time_sched, final_rows)
                    
    return final_rows
