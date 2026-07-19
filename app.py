import pandas as pd
import camelot
import re
import os
import sys
import platform
import subprocess
import unicodedata

# 1. 設定と準備
# KeyとPDFの紐付け辞書（[1]のロジック）
key_dict = {
    "関空免税店警備隊": "T1",
    # 必要に応じて追加
}

def normalize_text(text):
    return unicodedata.normalize('NFKC', str(text)).replace(" ", "").replace(" ", "")

def open_pdf_for_viewing(pdf_path):
    if platform.system() == 'Windows': os.startfile(pdf_path)
    elif platform.system() == 'Darwin': subprocess.call(['open', pdf_path])
    else: subprocess.call(['xdg-open', pdf_path])

# [1]. 時程表の読み込み（メモリ保持）
def load_schedule_table(file_path):
    # Googleスプレッドシート等を読み込む想定
    # 実際の環境に合わせてpd.read_excel等のパスを指定
    try:
        df = pd.read_excel(file_path, sheet_name='time_schdule')
        return df
    except Exception as e:
        print(f"時程表の読み込みに失敗しました: {e}")
        sys.exit()

# [2]. PDF解析と最大日付抽出
def extract_shift_info(pdf_path, search_key, df_schedule):
    tables = camelot.read_pdf(pdf_path, pages='all', flavor='stream')
    target_key = normalize_text(search_key)
    
    key_row_idx = -1
    target_table = None
    
    # Key行の特定
    for table in tables:
        df = table.df
        for i, row in df.iterrows():
            if target_key in normalize_text(row[0]):
                key_row_idx = i
                target_table = df
                break
        if key_row_idx != -1: break
            
    if key_row_idx == -1:
        print(f"Key '{search_key}' が見つかりません。")
        open_pdf_for_viewing(pdf_path)
        sys.exit()

    # 名前行（Key行の次行以降）を探索し、その間の範囲で最大日付を探す
    max_date = 0
    date_found = False
    
    # Key行から名前行出現までの範囲（5行程度と想定）を探索
    for i in range(key_row_idx, min(key_row_idx + 5, len(target_table))):
        for cell in target_table.iloc[i, :]:
            cell_str = str(cell)
            # 改行区切りの日付(数値)抽出
            parts = cell_str.split('\n')
            for part in parts:
                matches = re.findall(r'\b([1-9]|[1-2][0-9]|3[0-1])\b', part)
                for m in matches:
                    val = int(m)
                    if val > max_date:
                        max_date = val
                        date_found = True
                        
    if not date_found:
        print("日付データが見つかりませんでした。")
        open_pdf_for_viewing(pdf_path)
        sys.exit()
        
    return max_date

# --- メイン処理 ---
if __name__ == "__main__":
    # 時程表読み込み
    schedule_df = load_schedule_table('シフトカレンダー.xlsx')
    
    # 紐付け処理
    pdf_file = "免税店シフト表 1月度 第1ターミナル 2026.pdf"
    for key in key_dict.keys():
        print(f"解析中: {key}...")
        last_day = extract_shift_info(pdf_file, key, schedule_df)
        print(f"抽出完了: {key} の最終日付は {last_day} 日です。")
