import pandas as pd
import camelot
import re
import calendar

# =====================================================================
# [1] 時程表（スプレッドシートマスター）読込処理
# =====================================================================

def load_master_from_sheets(service, spreadsheet_id):
    """
    時程表（Googleスプレッドシート）を読み込み、
    勤務地をキー（T1, T2, 本町など）にした辞書構造を作成して登録する。
    """
    spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    time_dic = {}
    
    for s in spreadsheet.get('sheets', []):
        title = s.get("properties", {}).get("title")
        # A1:Z300 の範囲を余裕を持って読み込み
        res = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, 
            range=f"'{title}'!A1:Z300"
        ).execute()
        vals = res.get('values', [])
        if not vals: 
            continue
            
        df = pd.DataFrame(vals).fillna('')

        current_loc, start_idx = None, 0
        for i in range(len(df)):
            val_a = str(df.iloc[i, 0]).strip()
            if val_a != "":
                if current_loc:
                    time_dic[current_loc] = process_time_block(df.iloc[start_idx:i, :])
                current_loc, start_idx = val_a, i
        if current_loc:
            time_dic[current_loc] = process_time_block(df.iloc[start_idx:, :])
            
    return time_dic


def process_time_block(block):
    """
    時程表の時間表記（6=6:00, 6.25=6:15 などの浮動小数点）を
    正式な「HH:MM」の文字列形式に変換する補助関数。
    """
    def to_time(v):
        try:
            f = float(v)
            return f"{int(f):02d}:{int(round((f-int(f))*60)):02d}"
        except: 
            return v
            
    time_cols = []
    for col in range(3, block.shape[1]):
        try:
            float(block.iloc[0, col])
            time_cols.append(col)
        except:
            if time_cols: 
                break
                
    res_df = block.iloc[:, [0, 1, 2] + time_cols].copy()
    for i in range(len(time_cols)):
        res_df.iloc[0, 3 + i] = to_time(res_df.iloc[0, 3 + i])
        
    return res_df


# =====================================================================
# [2] PDFシフト予定表ファイル読込 ＆ 各関門検証
# =====================================================================

def get_calc_date_info(y, m):
    """ファイル名（年月）から算出する論理上の「最終日付（日数）」と「最終曜日」を取得する"""
    _, last_day = calendar.monthrange(y, m)
    w_list = ["月", "火", "水", "木", "金", "土", "日"]
    last_w = w_list[calendar.weekday(y, m, last_day)]
    return last_day, last_w


def analyze_pdf_structure(pdf_path, y, m):
    """
    【第1関門 ＆ 第2関門】 一体型パースメインプログラム
    
    仕様：
      - [0,0]から日付、勤務地、曜日を正確に一括取得
      - 【第1関門】 計算上の月末(A) と PDF抽出結果(B) を連動照合
      - [0,0]から日付・曜日を除去して純粋な「勤務地(C)」を抽出
    """
    # 1. CamelotでPDFから表データを抽出
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    if not tables: 
        return None, "PDF表抽出失敗"
    df = tables[0].df
    
    # A：カレンダーから計算した論理上の月末日と曜日
    calc_last_day, calc_last_w = get_calc_date_info(y, m)
    
    # ----------------------------------------------------
    # 🌟 [0,0] 一括集約型・月末/曜日 抽出ロジック（第1関門）
    # ----------------------------------------------------
    cell_0_0 = str(df.iloc[0, 0]).strip()
    
    # [0,0] セルからすべての「数字」を抽出して最大値を月末日(B)とする
    all_digits = [int(d) for d in re.findall(r'\d+', cell_0_0)]
    pdf_last_day = max(all_digits) if all_digits else 0
    
    # [0,0] セルからすべての「曜日」を抽出して最後の文字を月末曜日(B)とする
    all_weeks = re.findall(r'[月火水木金土日士]', cell_0_0)
    pdf_last_w = all_weeks[-1] if all_weeks else ""
    
    # フォント誤認識「士」を「土」に自動補正
    if pdf_last_w == "士":
        pdf_last_w = "土"

    # 【第1関門】照合チェック
    if not (pdf_last_day == calc_last_day and pdf_last_w == calc_last_w):
        error_msg = f"不一致：計算上の月末={calc_last_day}日({calc_last_w}) ／ PDF[0,0]から抽出={pdf_last_day}日({pdf_last_w})"
        return None, error_msg

    # ----------------------------------------------------
    # 🌟 勤務地(C)の純粋抽出（第2関門用）
    # ----------------------------------------------------
    # 独立した日付数字を除去
    location_c = re.sub(r'\b([1-9]|[12][0-9]|3[01])\b', '', cell_0_0)
    # 曜日文字とカッコを除去
    location_c = re.sub(r'\(?[月火水木金土日士]\)?', '', location_c)
    # 不要な文字やスペース・改行を大掃除して純粋なキーを抽出
    location_c = re.sub(r'[年月日で\s/：:・_ー~～-]', '', location_c).strip()
    
    # ----------------------------------------------------
    # 後続処理のためのデータマトリクス再構築
    # ----------------------------------------------------
    rows = []
    rows.append([""] + df.iloc[0, 1:].tolist()) 
    rows.append([location_c] + df.iloc[1, 1:].tolist())
    
    staff_names = []
    for i in range(2, len(df)):
        cell = str(df.iloc[i, 0]).strip()
        # 偶数行は「名前行」であるため、セル内改行があれば最初の要素（名前）のみを取得
        val = cell.split('\n')[0] if i % 2 == 0 else cell
        rows.append([val] + df.iloc[i, 1:].tolist())
        
        # スタッフ名リストを生成（ヘッダー等のノイズを除外）
        if i % 2 == 0 and val and val != location_c and not re.search(r'警備隊|株式会社|総括|予定表', val):
            staff_names.append(val)
            
    result_data = {
        "df": pd.DataFrame(rows), 
        "location": location_c, 
        "staff_list": staff_names
    }
    
    return result_data, "通過"


# =====================================================================
# [3] 特定スタッフの個別シフト・他スタッフシフトの分離抽出
# =====================================================================

def extract_target_data(df, target_staff, location):
    """
    【第3関門】
    選択された本人のシフト（2行分）と、他スタッフのシフト（各1行）を
    DataFrameから分離・抽出する。
    """
    if target_staff not in df[0].values:
        return None
        
    idx = df[df[0] == target_staff].index[0]
    my_daily_shift = df.iloc[idx : idx+2, 1:].copy()
    
    other_indices = []
    for i in range(2, len(df), 2):
        val_0 = str(df.iloc[i, 0]).strip()
        if i != idx and val_0 != location and val_0 != "" and not re.search(r'警備隊|株式会社|総括|予定表', val_0):
            other_indices.append(i)
            
    other_daily_shift = df.iloc[other_indices, :].copy()
    
    return {
        "my_daily_shift": my_daily_shift,
        "other_daily_shift": other_daily_shift
    }


# =====================================================================
# [4] Googleカレンダー登録用CSVデータの自動生成
# =====================================================================

def generate_calendar_records(year, month, location, time_schedule_df, my_daily_shift_df, other_staff_shift_df):
    """
    抽出されたシフト記号と時程表、他スタッフの動きを全自動で突き合わせ、
    Googleカレンダーインポート用CSVデータを生成する。
    """
    final_rows = []
    time_shift = time_schedule_df.fillna("").astype(str)
    
    for col_idx in my_daily_shift_df.columns:
        try:
            day_num = int(col_idx)
        except ValueError:
            continue
            
        target_date = f"{year}/{month:02d}/{day_num:02d}"
        
        info = str(my_daily_shift_df.iloc[0, col_idx-1]).strip()
        sub_info = str(my_daily_shift_df.iloc[1, col_idx-1]).strip()
        
        # "なし" の表記ゆれ自動マージ消去
        if info == "なし": info = ""
        if sub_info == "なし": sub_info = ""
        
        # 休み関連のスキップ判定
        if info in ["休", "休日", "公休", "有給", "有休", "他", ""]:
            continue
            
        # 本町シフトの特殊処理
        if info == "本町":
            final_rows.append(["本町", target_date, "", target_date, "", "True", "1行上=本町", "本町"])
            maru = re.findall(r'[①-⑨]', sub_info)
            desc_val = f"休憩={maru[0]}" if maru else ""
            final_rows.append(["本町", target_date, "09:00", target_date, "14:00", "False", desc_val, "本町"])
            continue
            
        # 通常のシフトコードの処理（時程表とのマッピング）
        if (time_shift.iloc[:, 1] == info).any():
            final_rows.
