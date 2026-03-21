import camelot
import pandas as pd
import pdfplumber
import re
import io
import numpy as np

def pdf_reader(pdf_stream, target_staff):
    clean_target = re.sub(r'[\s　]', '', str(target_staff))
    
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
        
    tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    table_dictionary = {}
    
    for i, table in enumerate(tables):
        df = table.df
        if not df.empty:
            text = str(df.iloc[0, 0])
            lines = text.splitlines()
            target_index = text.count('\n') // 2
            work_place = lines[target_index] if target_index < len(lines) else (lines[-1] if lines else "empty")
            df.iloc[0, 0] = work_place
            df = df.fillna('')

            # 検索用列の作成（全角半角スペース除去）
            search_col = df.iloc[:, 0].astype(str).apply(lambda x: re.sub(r'[\s　]', '', x))

            matched_indices = df.index[search_col == clean_target].tolist()
        
            if matched_indices:
                idx = matched_indices[0]
                last_idx = df.index[-1]
                            
                if idx == last_idx:
                    my_daily_shift = df.iloc[idx : idx+1].copy()
                else:
                    my_daily_shift = df.iloc[idx : idx+2].copy()
            
                # 自分を除外し、かつ表のヘッダーも除外
                other_daily_shift = df[(search_col != clean_target) & (df.index != 0)].copy()

                my_daily_shift = my_daily_shift.reset_index(drop=True)
                other_daily_shift = other_daily_shift.reset_index(drop=True)
                                        
                table_dictionary[work_place] = [my_daily_shift, other_daily_shift]
        
    return table_dictionary

# --- 他の関数（extract_year_month, time_schedule_from_drive, data_integration）は文法上の問題はないため、そのまま利用可能です ---
