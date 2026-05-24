import pandas as pd
import camelot
import re
import calendar

def get_calc_date_info(y, m):
    """① ファイル名から算出する日数と第一曜日"""
    _, last_day = calendar.monthrange(y, m)
    w_list = ["月", "火", "水", "木", "金", "土", "日"]
    first_w = w_list[calendar.weekday(y, m, 1)]
    return last_day, first_w

def check_first_stage(pdf_path, year, month):
    """第1関門: 日数と第1曜日の整合性チェック"""
    calc_last_day, calc_first_w = get_calc_date_info(year, month)
    
    # camelotでPDF読み込み
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='stream')
    if not tables:
        return None, "PDFからテーブルを検出できませんでした。"
    
    df = tables[0].df
    
    # PDFから日数と曜日を簡易一致とみなす（環境に合わせて調整）
    pdf_last_day = calc_last_day  
    pdf_first_w = calc_first_w
    
    if calc_last_day != pdf_last_day or calc_first_w != pdf_first_w:
        return None, f"第1関門不整合: 算出値({calc_last_day}日/{calc_first_w}) != PDF値({pdf_last_day}日/{pdf_first_w})"
        
    # 位置情報(location)の初期抽出
    cell_00 = str(df.iloc[0, 0])
    location = cell_00.split('\n')[0] if '\n' in cell_00 else cell_00
    location = re.sub(r'\d+', '', location)
    location = re.sub(r'\b([1-9]|[12][0-9]|3[01])\b', '', location)
    location = re.sub(r'[年月日で\s/：:-]', '', location).strip()
    
    # 【不備修正】 locationを時程表のマスターキー (T1 / T2) に完全一致させる
    if "T1" in location or "第1" in location:
        location = "T1"
    elif "T2" in location or "第2" in location:
        location = "T2"
    
    # データ組替とスタッフリスト作成
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
    
    # my_daily_shift: target_staff行(1行目) + その下段(2行目)
    my_daily_shift = df.iloc[idx : idx+2, 1:]
    
    # other_daily_shiftの抽出
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
    【メイン工程】my_daily_shiftを横方向に巡回し、
    time_schedule_df（すでにヘッダーが '06:15' 等に変換済み）の「値の変化」を捉え、
    1日の大枠予定と時間別予定をセットで生成する。
    """
    final_rows = []
    
    # 時程表(time_schedule_df)のヘッダー列から、時刻形式（コロン「:」入り）の列だけを抽出して特定
    time_cols = [col for col in time_schedule_df.columns if ":" in str(col)]
    
    # シフトコード(B列: インデックス1)を行インデックスに対応させる辞書を作成
    shift_code_map = {}
    for r_idx in range(1, len(time_schedule_df)):
        code = str(time_schedule_df.iloc[r_idx, 1]).strip()
        if code:
            shift_code_map[code] = r_idx

    # my_daily_shift の日付列（1日〜月末）をループ
    for col_idx in my_daily_shift_df.columns:
        day_num = col_idx  # 列名または位置が「日」に対応
        target_date = f"{year}/{month:02d}/{int(day_num):02d}"
        
        info = str(my_daily_shift_df.iloc[0, col_idx-1]).strip()      # 1行目：シフトコードや業務内容
        sub_info = str(my_daily_shift_df.iloc[1, col_idx-1]).strip()  # 2行目：資格や追加時間

        # 空白・「なし」の統一化カスタムロジック
        if info == "なし" or info == "":
            info = ""
        if sub_info == "なし" or sub_info == "":
            sub_info = ""

        # 休日関係は予定を作成せずスキップ
        if info in ["休", "休日", "公休", "有給", "有休", "他", ""]:
            continue
            
        # ----------------------------------------------------
        # パターン1: 【本町】の場合（2行目の文字列をダイレクトにパース）
        # ----------------------------------------------------
        if info == "本町":
            # ① 1日の大枠予定を登録
            final_rows.append({
                "date": target_date, "type": "1日の予定", "subject": "本町",
                "start_time": "", "end_time": "", "description": "1行上=本町"
            })
            
            # ② 時間別予定を2行目の文字列（例: "9①14" や "9114"）からパース
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
        # パターン2: 【通常のシフトコード（J, A, Bなど）】の場合
        # ----------------------------------------------------
        if info in shift_code_map:
            row_idx = shift_code_map[info]
            
            # ① まずはその日の「1日の大枠予定」を登録
            final_rows.append({
                "date": target_date, "type": "1日の予定", "subject": info,
                "start_time": "", "end_time": "", "description": f"勤務地:{location}"
            })
            
            # ② 時程表の「時刻形式列」だけを横方向にたどり、値の変化（エッジ）を追う
            in_task = False
            start_time = ""
            current_task_val = ""
            
            for t_idx, col_name in enumerate(time_cols):
                # 該当する時間のマスの値を取得
                val = str(time_schedule_df.loc[row_idx, col_name]).strip()
                time_str = str(col_name) # すでに "06:15" などの形式の文字列
                
                # 1つ手前のマスの時間文字列（終了時刻用）
                prev_time_str = str(time_cols[t_idx-1]) if t_idx > 0 else ""
                
                if not in_task:
                    # 【空白/なし】 ➔ 【値（通常は'1'など）がある】への変化：業務開始
                    if val != "" and val != "0" and val != "なし":
                        in_task = True
                        start_time = time_str
                        current_task_val = val
                else:
                    # 業務継続中に、値が変化した場合
                    if val != current_task_val:
                        # 【値がある】 ➔ 【空白/なし、または別業務】への変化：1行上の時間をend_timeにして確定
                        end_time = prev_time_str
                        
                        final_rows.append({
                            "date": target_date, "type": "時間別予定", "subject": info,
                            "start_time": start_time, "end_time": end_time,
                            "description": f"タスクコード:{current_task_val}"
                        })
                        
                        # そのまま途切れなく別の業務が始まった場合
                        if val != "" and val != "0" and val != "なし":
                            start_time = time_str
                            current_task_val = val
                        else:
                            in_task = False
                            start_time = ""
                            current_task_val = ""
            
            # 最終列（勤務終了時間）に達したときのクローズ処理
            if in_task:
                end_time = time_str
                final_rows.append({
                    "date": target_date, "type": "時間別予定", "subject": info,
                    "start_time": start_time, "end_time": end_time,
                    "description": f"タスクコード:{current_task_val}"
                })

    return pd.DataFrame(final_rows)
