import pandas as pd
import camelot
import re
import calendar

def get_calc_date_info(y, m):
    """① ファイル名から算出する日数と第一曜日"""
    # 月の末日を取得
    _, last_day = calendar.monthrange(y, m)
    # 1日の曜日インデックスを取得 (0:月, 1:火, 2:水, 3:木, 4:金, 5:土, 6:日)
    w_idx = calendar.weekday(y, m, 1)
    w_list = ["月", "火", "水", "木", "金", "土", "日"]
    first_w = w_list[w_idx]
    return last_day, first_w

def analyze_pdf_structure(pdf_path, y, m):
    """第1関門・第2関門の実行とデータの再構成"""
    # PDF読込
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    if not tables:
        return None, "PDFから表を抽出できませんでした。"
    
    df = tables[0].df
    # [0,0]の値を正規化
    raw_0_0 = str(df.iloc[0, 0]).replace('\n', ' ').strip()
    
    # --- 第1関門：算出値とPDF内容の照合 ---
    calc_last_day, calc_first_w = get_calc_date_info(y, m)
    
    # PDFの[0,0]から数値をすべて拾い、その最大値を末日とする
    days_in_pdf = [int(n) for n in re.findall(r'\d+', raw_0_0)]
    pdf_last_day = max(days_in_pdf) if days_in_pdf else 0
    # PDFの[0,0]から最初に出現する曜日を第一曜日とする
    pdf_first_w_match = re.search(r'[月火水木金土日]', raw_0_0)
    pdf_first_w = pdf_first_w_match.group() if pdf_first_w_match else ""

    # 判定
    if pdf_last_day != calc_last_day or pdf_first_w != calc_first_w:
        return None, f"第1関門不通過: 算出={calc_last_day}{calc_first_w} / PDF={pdf_last_day}{pdf_first_w}"

    # --- 第2関門：location抽出（曜日と日付の除去） ---
    location = raw_0_0
    # 1. 曜日文字列をすべて削除
    location = re.sub(r'[月火水木金土日]', '', location)
    # 2. 曜日と同数程度存在する日付文字列(1-31)をワード境界(\b)で削除
    location = re.sub(r'\b(?:[1-9]|[12][0-9]|3[01])\b', '', location)
    # 3. その他不要語句の掃除
    location = re.sub(r'[年月日で\s/：:-]|勤務予定表|～|~', '', location).strip()

    # --- データの組み替え（app (18).pyの仕様を継承） ---
    rows = []
    rows.append([""] + df.iloc[0, 1:].tolist()) # 0行目は空文字
    rows.append([location] + df.iloc[1, 1:].tolist()) # 1行目にlocation
    
    staff_names = []
    for i in range(2, len(df)):
        cell = str(df.iloc[i, 0]).strip()
        # 氏名行(偶数)なら改行で分割して先頭を取得
        val = cell.split('\n')[0] if i % 2 == 0 else cell
        rows.append([val] + df.iloc[i, 1:].tolist())
        
        # スタッフリスト作成（偶数行、かつ空でない、かつlocationでない）
        if i % 2 == 0 and val and val != location:
            staff_names.append(val)
            
    return {
        "df": pd.DataFrame(rows), 
        "location": location, 
        "staff_list": staff_names, 
        "raw_0_0": raw_0_0
    }, "通過"
