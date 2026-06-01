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
    勤務地をキー（T1, T2など）にした辞書構造を作成して登録する。
    """
    spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    time_dic = {}
    
    for s in spreadsheet.get('sheets', []):
        title = s.get("properties", {}).get("title")
        # A1:Z300 の範囲を読み込み
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
# [2] PDFシフト予定表ファイル読込 ＆ 第1関門検証
# =====================================================================

def get_calc_date_info(y, m):
    """【値A】入力・取得された年月から算出する論理上の「最終日付」と「最終曜日」を取得する"""
    _, last_day = calendar.monthrange(y, m)
    w_list = ["月", "火", "水", "木", "金", "土", "日"]
    last_w = w_list[calendar.weekday(y, m, last_day)]
    return last_day, last_w


def check_first_gate(pdf_path, y, m):
    """
    【第1関門】検証プログラム
    
    仕様：
      - CamelotでPDFの表データを読み込む。
      - [0,0]セルから1~月末までの日付文字列、曜日、勤務地が含まれる塊を取得。
      - 【値A】指定年月から計算した最終日付・最終曜日
      - 【値B】PDFの[0,0]セルから抽出した最終日付・最終曜日
      - A=Bなら通過、A≠Bならエラー理由を返して停止。
    """
    # 1. Camelotを使用して読込
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    if not tables: 
        return False, "PDFから表構造を抽出できませんでした（Camelot読込失敗）。"
    
    df = tables[0].df
    cell_0_0 = str(df.iloc[0, 0]).strip()
    
    # A：取得した年月から最終日付と最終曜日を取得する
    calc_last_day, calc_last_w = get_calc_date_info(y, m)
    
    # B：読み込んだpdfシフト表ファイル[0,0]から最終日付と最終曜日を取得する
    # セル内のすべての数字を抽出して、その最大値を月末日とする
    all_digits = [int(d) for d in re.findall(r'\d+', cell_0_0)]
    pdf_last_day = max(all_digits) if all_digits else 0
    
    # セル内のすべての曜日文字を抽出して、最後の文字を月末曜日とする
    all_weeks = re.findall(r'[月火水木金土日士]', cell_0_0)
    pdf_last_w = all_weeks[-1] if all_weeks else ""
    
    # フォント誤認識「士」を「土」に自動補正
    if pdf_last_w == "士":
        pdf_last_w = "土"

    # A＝B ならそのまま通過。A≠B なら理由を返却。
    if pdf_last_day == calc_last_day and pdf_last_w == calc_last_w:
        return True, "通過"
    else:
        error_reason = (
            f"最終日付または最終曜日が一致しません。\n"
            f"【計算値A】: {calc_last_day}日 ({calc_last_w})\n"
            f"【PDF検出値B】: {pdf_last_day}日 ({pdf_last_w})"
        )
        return False, error_reason
