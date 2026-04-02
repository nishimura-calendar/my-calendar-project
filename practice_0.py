import pandas as pd
import pdfplumber
import unicodedata
import re

# --- 比較用正規化 ---
def normalize_for_match(text):
    if text is None or str(text).lower() == 'nan': return ""
    normalized = unicodedata.normalize('NFKC', str(text))
    return re.sub(r'\s+', '', normalized).strip().upper()

# --- 確定したメインロジック ---
def process_daily_shift(items, loc_name, date_str, master_df, master_areas_norm, my_daily_shift, other_staff_shift, shift_cal_func):
    final_rows = []
    
    for item in items:
        if not item:
            continue
            
        norm_item = normalize_for_match(item)
        
        # --- 分岐1：time_scheduleのB列（巡回区域）にあるか判定 ---
        if norm_item in master_areas_norm:
            # 1. 終日イベントを追加（Subject = 拠点名+値, Location = ""）
            final_rows.append([
                f"{loc_name}+{item}", # Subject
                date_str, "", date_str, "", "True", "", ""
            ])
            
            # 2. 【打合.py参照】時程表に沿って詳細な引き継ぎ処理（False行）を生成
            # ここで外部の shift_cal を呼び出します
            shift_cal_func(loc_name, date_str, item, my_daily_shift, other_staff_shift, master_df, final_rows)
            
        else:
            # --- B列にない場合（有休、本町、その他のメモなど） ---
            # 1. 終日イベントを追加（Subject = 値そのまま, Location = ""）
            final_rows.append([
                item, 
                date_str, "", date_str, "", "True", "", ""
            ])

            # --- 分岐2：もし "本町" なら時間指定の追加処理 ---
            if "本町" in item:
                # 時程表ヘッダーから拠点全体の開始(D列)・終了(最終列)時間を取得
                # ※master_dfの構造に合わせて調整
                try:
                    start_t = master_df.iloc[0, 3] 
                    end_t = master_df.iloc[0, -1]
                except:
                    start_t, end_t = "", ""
                
                # 詳細時間を持つイベント行を追加
                final_rows.append([
                    item, 
                    date_str, start_t, date_str, end_t, "False", "", ""
                ])
                
    return final_rows
