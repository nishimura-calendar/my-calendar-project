import pandas as pd
import camelot
import re
import calendar

# --- 省略（get_calc_date_info, load_master_from_sheets 等） ---

def analyze_pdf_structure(pdf_path, y, m):
    """第一関門判定・location抽出・スタッフ抽出"""
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    if not tables: return None, "PDF表抽出失敗"
    df = tables[0].df
    raw_0_0 = str(df.iloc[0, 0]).strip()
    
    # 【手順1】先に location (例: T1) を確定させる[cite: 7]
    loc = re.sub(r'\(?[月火水木金土日]\)?', '', raw_0_0)
    loc = re.sub(r'\d+[\s～~-]+\d+', '', loc)
    loc = re.sub(r'\b([1-9]|[12][0-9]|3[01])\b', '', loc)
    location = re.sub(r'[年月日で\s/：:-]', '', loc).strip()
    
    # 【手順2】第一関門：日付・曜日判定[cite: 7]
    # (既存の判定ロジック)

    # 【手順3】第3関門：スタッフ名リスト作成（locationと一致するものは入れない）
    staff_names = []
    for i in range(2, len(df), 2):
        # セル内の改行で分割し、名前部分のみ取得して空白除去
        name_in_cell = str(df.iloc[i, 0]).split('\n')[0].strip()
        
        # 名前が空でなく、かつ location (T1) と完全に一致しない場合のみ追加
        if name_in_cell and name_in_cell != location:
            staff_names.append(name_in_cell)
    
    # データ組替処理[cite: 7]
    rows = []
    rows.append([""] + df.iloc[0, 1:].tolist()) 
    rows.append([location] + df.iloc[1, 1:].tolist()) 
    for i in range(2, len(df)):
        cell = str(df.iloc[i, 0]).strip()
        val = cell.split('\n')[0] if i % 2 == 0 else cell
        rows.append([val] + df.iloc[i, 1:].tolist())
            
    return {"df": pd.DataFrame(rows), "location": location, "staff_list": staff_names}, "通過"
