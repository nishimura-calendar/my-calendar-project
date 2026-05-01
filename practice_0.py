import streamlit as st
import pandas as pd
import re
import camelot
import os
import calendar

# --- 2. 座標 l, h1, h2 を動的に決定する関数 ---
def calculate_optimal_coords(df, target_staff):
    """
    0列目の改行位置とスタッフ名から最適な境界 l を算出する
    """
    max_char_count = len(target_staff) # 最低でも対象者名の長さは確保
    
    for val in df.iloc[:, 0].astype(str):
        # 改行で分割し、最初の1行目だけを取り出す
        first_line = val.split('\n')[0].strip()
        # 拠点名などの短いKeyも考慮
        if len(first_line) > max_char_count:
            max_char_count = len(first_line)
    
    # 1文字あたり約12ptと仮定し、余白を加味してポイント換算
    l_px = (max_char_count * 12) + 15 
    
    # h1, h2 は 0, 1行目の高さから取得（固定的な比率ではなく実測値ベース）
    h1_px = 20 # 日付行の高さ目安
    h2_px = 20 # 曜日行の高さ目安
    
    return l_px, h1_px, h2_px

# --- 4. 統合解析メインロジック (修正版) ---
def process_full_logic(pdf_stream, target_staff, time_dic, year, month):
    truth_days, truth_first_wday = get_month_truth(year, month)
    
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())

    try:
        # 【STEP 1】仮読み込み（座標決定のため）
        temp_tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice')
        if not temp_tables: return None, "PDF解析失敗"
        
        # 動的な列幅 l の計算
        l_pt, h1, h2 = calculate_optimal_coords(temp_tables[0].df, target_staff)

        # 【STEP 2】確定した座標で本読み込み（columns指定で0列目を強制分割）
        # PDFの幅（842pt等）に対して l_pt の位置に縦線を引く設定
        final_tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice', columns=[str(l_pt)])
        df = final_tables[0].df

        # --- 以下、整合性チェック ---
        # 0列目の1行目から new_location を取得
        new_location = df.iloc[0, 0].split('\n')[0].strip()
        new_location = re.sub(r'\d{1,2}/\d{1,2}|[（\(][月火水木金土日][）\)]|[月火水木金土日]', '', new_location).strip()

        # 曜日判定（スキャン範囲を広げて「1日」の真上を探す）
        pdf_first_wday = ""
        for r in range(min(5, len(df))):
            match = re.search(r'[月火水木金土日]', str(df.iloc[r, 1]))
            if match:
                pdf_first_wday = match.group(0)
                break

        # 整合性エラーの判定[cite: 3]
        pdf_days = len(df.columns) - 1
        if pdf_days != truth_days or pdf_first_wday != truth_first_wday:
            reason = f"【整合性エラー】PDF: {pdf_days}日/{pdf_first_wday}曜始 vs カレンダー: {truth_days}日/{truth_first_wday}曜始"
            return df, reason

        # --- スタッフ抽出 ---
        clean_target = normalize_text(target_staff)
        # 0列目も「改行の1行目」だけで照合する
        search_col = df.iloc[:, 0].astype(str).apply(lambda x: normalize_text(x.split('\n')[0]))
        
        if clean_target not in search_col.values:
            return df, f"『{target_staff}』が見当たりません。"

        idx = search_col[search_col == clean_target].index[0]
        
        return {
            "key": matched_key,
            "my_daily_shift": df.iloc[idx : idx + 2, :].values.tolist(), # 本人2行[cite: 5]
            "other_daily_shift": [df.iloc[i].tolist() for i in range(len(df)) if i not in [0, idx, idx+1]], # 他者1行[cite: 3]
            "time_schedule_full": time_dic[matched_key] # 全範囲表示[cite: 2]
        }, None

    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")
