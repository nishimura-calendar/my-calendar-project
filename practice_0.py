import pandas as pd
import pdfplumber
import unicodedata
import re

def normalize_for_match(text):
    """比較用にテキストを正規化（全角半角統一、空白・改行除去）"""
    if text is None or str(text).lower() == 'nan': 
        return ""
    normalized = unicodedata.normalize('NFKC', str(text))
    return re.sub(r'[\s\n]+', '', normalized).strip().upper()

def pdf_reader(file_stream, target_staff):
    """
    1. ページ内のテーブルをスキャン
    2. 名前が見つかったテーブルを特定
    3. 左上セル(0,0)の改行数をカウントし、その半分(count // 2)の位置から勤務地を抽出
    """
    table_dictionary = {}
    clean_target = normalize_for_match(target_staff)

    with pdfplumber.open(file_stream) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                df = pd.DataFrame(table)
                if df.empty: continue
                
                # 0列目を氏名として検索
                search_col = df.iloc[:, 0].apply(normalize_for_match)
                found_indices = [i for i, val in enumerate(search_col) if clean_target in val]
                
                if found_indices:
                    # --- 勤務地の特定ロジック (改行カウント方式) ---
                    # 例: "1\n\nT2\n\n木" -> 改行4つ -> 4//2 = 2 -> lines[2] が "T2"
                    header_cell = str(df.iloc[0, 0])
                    lines = header_cell.split('\n')
                    
                    try:
                        num_newlines = header_cell.count('\n')
                        target_index = num_newlines // 2
                        
                        # 指定されたインデックスから勤務地を取得
                        if target_index < len(lines):
                            work_place = lines[target_index].strip()
                        else:
                            work_place = lines[-1].strip() if lines else "empty"
                            
                        # もし空文字だった場合は、前後で空でないものを探す(フォールバック)
                        if not work_place:
                            non_empty_elements = [e.strip() for e in lines if e.strip()]
                            # 日付、勤務地、曜日の順ならインデックス1が勤務地
                            work_place = non_empty_elements[1] if len(non_empty_elements) >= 2 else non_empty_elements[0]
                    except Exception:
                        work_place = "解析エラー"
                    
                    for idx in found_indices:
                        my_data = df.iloc[[idx]].copy()
                        others_data = df[df.index != idx].copy()
                        
                        # 特定した勤務地をキーとして辞書を作成
                        table_dictionary[work_place] = [
                            my_data.reset_index(drop=True), 
                            others_data.reset_index(drop=True)
                        ]
                        
    return table_dictionary
