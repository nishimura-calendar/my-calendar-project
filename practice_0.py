import pandas as pd
import re
import unicodedata
import os
import camelot
import math

def normalize_text(text):
    if not isinstance(text, str): return ""
    text = unicodedata.normalize('NFKC', text)
    return re.sub(r'[\s　]', '', text).lower()

def pdf_reader(pdf_stream, target_staff, time_dic):
    """
    【最終定義ロジック】
    1. 勤務地: iloc[0,0]から時程表keyを照合して特定
    2. 日付: iloc[0, 1]から右へ
    3. 曜日: iloc[1, 1]から日付の下へ
    4. 描画座標計算: 勤務地/名前の最大長、文字高さを基準に算出
    """
    pdf_stream.seek(0)
    temp_name = "temp_process.pdf"
    with open(temp_name, "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    try:
        tables = camelot.read_pdf(temp_name, pages='all', flavor='lattice')
        res = {}
        
        for table in tables:
            df = table.df
            if df.empty: continue
            
            # --- 第1関門: 勤務地の特定 (時程表マスターと照合) ---
            # iloc[0,0]の混在文字列から、time_dicのkeyが含まれているか探す
            cell_0_0_raw = str(df.iloc[0, 0])
            work_place = "Unknown"
            found_key = None
            
            for t_key in time_dic.keys():
                if t_key in cell_0_0_raw: # 時程表のkeyが含まれていればそれを勤務地とする
                    work_place = t_key
                    found_key = normalize_text(t_key)
                    break
            
            if not found_key:
                continue # 勤務地が特定できない表はスキップ
            
            # --- 日付と曜日の抽出 ---
            # 日付: iloc[0, 1:] / 曜日: iloc[1, 1:]
            dates = df.iloc[0, 1:].tolist()
            weeks = df.iloc[1, 1:].tolist()
            
            # --- 座標計算 (中線・罫線) ---
            # 1. 名前の最長長さを取得
            search_col = df.iloc[:, 0].astype(str)
            max_name_len = search_col.apply(len).max()
            wp_len = len(work_place)
            
            # 中線の開始位置 x座標 (切り上げ)
            x_border = math.ceil(max(wp_len, max_name_len))
            
            # 仮定の文字高さ (実際のPDFから取得できない場合は基準値を設定)
            char_height_date = 10.0 # 日付文字の最高値(仮)
            char_height_week = 10.0 # 曜日文字の最高値(仮)
            
            # y座標 (日付の文字の最高値を切り上げた高さ)
            y_mid_line = math.ceil(char_height_date)
            
            # iloc[1,0]の底罫線
            bottom_border = math.ceil(char_height_date + char_height_week)
            
            # --- スタッフ抽出 (第3関門) ---
            clean_target = normalize_text(target_staff)
            target_indices = df.index[search_col.apply(normalize_text) == clean_target].tolist()
            
            if target_indices:
                idx = target_indices[0]
                my_shift = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
                others = df.drop([0, idx, idx+1] if idx+1 < len(df) else [0, idx]).copy().reset_index(drop=True)
                
                # 計算した座標情報を付加して保存
                res[found_key] = {
                    "my_shift": my_shift,
                    "others": others,
                    "wp_name": work_place,
                    "drawing_info": {
                        "x_border": x_border,
                        "y_mid_line": y_mid_line,
                        "bottom_border": bottom_border
                    }
                }
        return res
    finally:
        if os.path.exists(temp_name): os.remove(temp_name)
