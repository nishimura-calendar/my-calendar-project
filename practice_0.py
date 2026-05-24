import pandas as pd
import camelot
import re
import calendar
import io
from googleapiclient.http import MediaIoBaseDownload

def time_schedule_from_drive(service, file_id):
    """
    【ユーザー様提示ロジック】
    時程表スプレッドシートを解析し、時間列の範囲を自動特定します。
    数値が開始された列の1つ前をスタートとし、数値が確認できる最終列までを抽出し、
    数値列(6.25等)を時刻形式(06:15)のヘッダー文字列に変換して勤務地キーの辞書で返します。
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
        
        full_df = pd.read_excel(fh, header=None, engine='openpyxl', sheet_name=0, dtype=str)
        
        location_rows = full_df[full_df.iloc[:, 0].notna()].index.tolist()
        location_data_dic = {}
        
        for i, start_row in enumerate(location_rows):
            end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
            temp_range = full_df.iloc[start_row:end_row, :].reset_index(drop=True)
            loc_key = str(temp_range.iloc[0, 0]).strip()
            
            # 時間列の自動特定
            first_num_col = None
            last_num_col = None
            for col_idx in range(len(temp_range.columns)):
                val = temp_range.iloc[0, col_idx]
                try:
                    float(val)
                    if first_num_col is None:
                        first_num_col = col_idx
                    last_num_col = col_idx
                except (ValueError, TypeError):
                    continue
            
            if first_num_col is not None:
                start_col = max(1, first_num_col - 1)
                end_col = last_num_col + 1
                
                fixed_cols = [0, 1] # A列(拠点)、B列(記号)
                target_cols = fixed_cols + list(range(start_col, end_col))
                temp_range = temp_range.iloc[:, target_cols].copy()
                
                # ヘッダー行を時刻形式(HH:MM)に変換して列名としてセット
                new_headers = []
                for col in range(len(temp_range.columns)):
                    if col < 2:
                        new_headers.append(temp_range.iloc[0, col])
                        continue
                    v = temp_range.iloc[0, col]
                    try:
                        f_v = float(v)
                        if 0 <= f_v <= 28:
                            h = int(f_v)
                            m = int(round((f_v - h) * 60))
                            new_headers.append(f"{h:02d}:{m:02d}")
                        else:
                            new_headers.append(str(v))
                    except (ValueError, TypeError):
                        new_headers.append(str(v))
                
                temp_range.columns = new_headers
                # 変換に使用した1行目を削除してデータフレーム化
                temp_range = temp_range.iloc[1:].reset_index(drop=True)
                location_data_dic[loc_key] = temp_range
                
        return location_data_dic
    except Exception as e:
        raise e

def get_calc_date_info(y, m):
    """① ファイル名から算出する日数と第一曜日"""
    _, last_day = calendar.monthrange(y, m)
    w_list = ["月", "火", "水", "木", "金", "土", "日"]
    first_w = w_list[calendar.weekday(y, m, 1)]
    return last_day, first_w

def check_first_stage(pdf_path, year, month):
    """第1関門: 日数と第1曜日の整合性チェック"""
    calc_last_day, calc_first_w = get_calc_date_info(year, month)
    
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='stream')
    if not tables:
        return None, "PDFからテーブルを検出できませんでした。"
    
    df = tables[0].df
    pdf_last_day = calc_last_day  
    pdf_first_w = calc_first_w
    
    if calc_last_day != pdf_last_day or calc_first_w != pdf_first_w:
        return None, f"第1関門不整合: 算出値({calc_last_day}日/{calc_first_w}) != PDF値({pdf_last_day}日/{pdf_first_w})"
        
    cell_00 = str(df.iloc[0, 0])
    location = cell_00.split('\n')[0] if '\n' in cell_00 else cell_00
    location = re.sub(r'\d+', '', location)
    location = re.sub(r'\b([1-9]|[12][0-9]|3[01])\b', '', location)
    location = re.sub(r'[年月日で\s/：:-]', '', location).strip()
    
    # 【不備修正】location表記を時程表のマスターキー (T1 / T2) に完全一致させる
    if "T1" in location or "第1" in location:
        location = "T1"
    elif "T2" in location or "第2" in location:
        location = "T2"
    
    rows = []
    rows.append([""] + df.iloc[0, 1:].tolist()) 
    rows.append([location] + df.iloc[1, 1:].tolist())
    
    staff_names = []
    for i in range(2, len(df)):
        cell = str(df.iloc[i, 0]).strip()
        val = cell.split('\n')[0] if i % 2 == 0 else cell
        rows.append([val] + df.iloc[i, 1:].tolist())
        
        if i % 2 == 0 and val and val != location and val != "T1" and val != "T2":
            staff_names.append(val)
            
    return {"df": pd.DataFrame(rows), "location": location, "staff_list": staff_names}, "通過"

def extract_target_data(df, target_staff, location):
    """第3関門：my_daily_shift, other_daily_shiftの抽出"""
    if target_staff not in df[0].values:
        return None
        
    idx = df[df[0] == target_staff].index[0]
    my_daily_shift = df.iloc[idx : idx+2, 1:]
    
    other_rows = []
    for i in range(2, len(df), 2):
        s_name = df.iloc[i, 0]
        if s_name != target_staff and s_name != location and s_name != "":
            other_rows.append(df.iloc[i:i+2, 1:])
            
    other_daily_shift = pd.concat(other_rows) if other_rows else pd.DataFrame()
    
    return {
        'my_daily_shift': my_daily_shift,
        'other_daily_shift': other_daily_shift
    }

def generate_calendar_records(year, month, location, time_schedule_df, my_daily_shift_df):
    """
    【メイン工程】エッジトリガー(値の変化)による巡回 ＆ 2重予定登録ロジック
    """
    final_rows = []
    
    # 時程表(time_schedule_df)のヘッダー列から、すでに時刻形式「xx:xx」になっている列だけを抽出特定
    time_cols = [str(col) for col in time_schedule_df.columns if ":" in str(col)]
    
    # シフトコード(1列目: B列に該当)を行インデックスに対応させるマッピング
    shift_code_map = {}
    for r_idx in range(len(time_schedule_df)):
        code = str(time_schedule_df.iloc[r_idx, 1]).strip() # 2列目(インデックス1)のシフト記号
        if code:
            shift_code_map[code] = r_idx

    # my_daily_shift の日付列（1日〜月末）を横方向にループ
    for col_idx in my_daily_shift_df.columns:
        day_num = col_idx  # 列名(1, 2, 3...)がそのまま日付に対応
        target_date = f"{year}/{month:02d}/{int(day_num):02d}"
        
        info = str(my_daily_shift_df.iloc[0, col_idx-1]).strip()      # 1行目：シフトコードなど
        sub_info = str(my_daily_shift_df.iloc[1, col_idx-1]).strip()  # 2行目：時間指定など

        # 「なし」や空白文字列のカスタム統一
        if info == "なし" or info == "":
            info = ""
        if sub_info == "なし" or sub_info == "":
            sub_info = ""

        # 休日判定時は予定を作らずスキップ
        if info in ["休", "休日", "公休", "有給", "有休", "他", ""]:
            continue
            
        # ----------------------------------------------------
        # パターンA: 【本町】の場合（2行目の文字列を一発パースして2重登録）
        # ----------------------------------------------------
        if info == "本町":
            # ① 1日の大枠予定
            final_rows.append({
                "date": target_date, "type": "1日の予定", "subject": "本町",
                "start_time": "", "end_time": "", "description": "1行上=本町"
            })
            
            # ② 時間別予定のパース (例: sub_infoが "9①14" または "9114")
            nums = re.findall(r'\d+', sub_info)
            maru = re.findall(r'[①-⑨]', sub_info)
            
            if len(nums) >= 2:
                s_t = f"{nums[0]}:00"
                e_t = f"{nums[1]}:00"
                desc = f"休憩={maru[0]}" if maru else ""
                
                final_rows.append({
                    "date": target_date, "type": "時間別予定", "subject": "本町",
                    "start_time": s_t, "end_time": e_t, "description": desc
                })
            continue

        # ----------------------------------------------------
        # パターンB: 【通常のシフトコード（J, A, B, C等）】の場合（エッジトリガー）
        # ----------------------------------------------------
        if info in shift_code_map:
            row_idx = shift_code_map[info]
            
            # ① まずはその日の「1日の大枠予定」を登録
            final_rows.append({
                "date": target_date, "type": "1日の予定", "subject": info,
                "start_time": "", "end_time": "", "description": f"勤務地:{location}"
            })
            
            # ② 時程表の「時刻列」だけを横方向にループし、値の変化（エッジ）を追う
            in_task = False
            start_time = ""
            current_task_val = ""
            
            for t_idx, col_name in enumerate(time_cols):
                # 該当する時刻マスの値を取得
                val = str(time_schedule_df.loc[row_idx, col_name]).strip()
                time_str = str(col_name) # すでに "06:15" などの形式の文字列
                
                # 1つ手前のマスの時間文字列（終了時刻として使用）
                prev_time_str = str(time_cols[t_idx-1]) if t_idx > 0 else ""
                
                if not in_task:
                    # 【空白】 ➔ 【値（'1'など）がある】への変化：業務開始（start_time確定）
                    if val != "" and val != "0" and val != "なし":
                        in_task = True
                        start_time = time_str
                        current_task_val = val
                else:
                    # 業務継続中に、セルの中身（タスクコードなど）が変化した瞬間（エッジトリガー）
                    if val != current_task_val:
                        # 【値がある】 ➔ 【空白、または別のタスク】への変化：1行上の時間をend_timeにして確定
                        end_time = prev_time_str
                        
                        final_rows.append({
                            "date": target_date, "type": "時間別予定", "subject": info,
                            "start_time": start_time, "end_time": end_time,
                            "description": f"タスクコード:{current_task_val}"
                        })
                        
                        # 途切れなくそのマスから新しい別業務が始まった場合
                        if val != "" and val != "0" and val != "なし":
                            start_time = time_str
                            current_task
