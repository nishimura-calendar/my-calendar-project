import streamlit as st
import camelot
import io
import re

def parse_shift_pdf(pdf_file, valid_keys):
    # PDFをテキスト解析
    tables = camelot.read_pdf(io.BytesIO(pdf_file.read()), pages='all', flavor='stream')
    results = {key: {'max_date': 0, 'day_of_week': "不明"} for key in valid_keys}
    
    # 全ての表を走査
    for table in tables:
        df = table.df
        # 表の行をリスト化
        rows = df.values.tolist()
        
        for i, row in enumerate(rows):
            # 行内の全要素を文字列化し、不要な記号を除去
            clean_row = [str(val).replace('|', '').strip() for val in row]
            
            # 1. キー（T1など）がどこかにあるかチェック
            current_key = None
            for val in clean_row:
                if val in valid_keys:
                    current_key = val
                    break
            
            if not current_key:
                continue

            # 2. 数字を探す（日付行である可能性）
            nums = []
            for item in clean_row:
                # 数字のみを抽出 (例: "31" -> 31)
                found = re.findall(r'^\d+$', item)
                nums.append(int(found[0]) if found else -1)
            
            # 日付（1~31）が5つ以上並んでいれば日付行とみなす
            if len([n for n in nums if 1 <= n <= 31]) >= 5:
                max_d = max(nums)
                col_idx = nums.index(max_d)
                
                # 3. 直下の行から曜日を取得
                if i + 1 < len(rows):
                    next_row = [str(val).replace('|', '').strip() for val in rows[i+1]]
                    # 範囲外エラー防止
                    if col_idx < len(next_row):
                        results[current_key]['max_date'] = max_d
                        results[current_key]['day_of_week'] = next_row[col_idx]
                        
    return results

# UI表示部分（既存のロジックでOK）
# ...
