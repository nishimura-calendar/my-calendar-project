import streamlit as st
import pandas as pd
import camelot
import re
import unicodedata

# [1] 勤務地をKeyとして保持（辞書登録）
# 画面表示はせず、メモリ上の参照用として使用
KEY_MAPPING = {
    "関空免税店警備隊": "T1",
    "第2ターミナル": "T2" 
}

def normalize_text(text):
    return unicodedata.normalize('NFKC', str(text)).replace(" ", "").replace(" ", "")

# [2]〈1〉PDF解析と最大日付抽出
def extract_shift_date(pdf_file, search_key):
    # PDFを一時保存して解析
    with open("temp.pdf", "wb") as f:
        f.write(pdf_file.getbuffer())
    
    tables = camelot.read_pdf("temp.pdf", pages='all', flavor='stream')
    target_key = normalize_text(search_key)
    
    for table in tables:
        df = table.df
        for i, row in df.iterrows():
            if target_key in normalize_text(row[0]):
                # [2]〈2〉探索範囲の適正化
                # Key行の直後から名前行の手前（最大4行）に限定
                max_date = 0
                search_limit = min(i + 4, len(df))
                
                for row_idx in range(i + 1, search_limit):
                    for cell in df.iloc[row_idx, :]:
                        # 数値抽出（1-28に限定し31などの誤検知を防止）
                        matches = re.findall(r'\b([1-9]|[1-2][0-9])\b', str(cell))
                        for m in matches:
                            max_date = max(max_date, int(m))
                return max_date
    return None

# [2]〈3〉時程表との突合・不一致検出
def validate_schedule(pdf_max_date, scheduled_df):
    # 時程表（df）の最終列の日付とPDFから抽出したmax_dateを突合
    # 不一致の場合は警告フラグを返す
    try:
        # 時程表の最終列（日付列）を取得
        table_max_date = int(scheduled_df.columns[-1]) 
        if pdf_max_date != table_max_date:
            return False, f"日付不一致: PDF={pdf_max_date}, 時程表={table_max_date}"
        return True, "OK"
    except:
        return False, "時程表の日付解析エラー"

# --- ストリームリット実行部 ---
if __name__ == "__main__":
    # 時程表データは事前にロードされている前提 (data_dict)
    # 選択された勤務地に基づき上記関数を呼び出す
    pass
