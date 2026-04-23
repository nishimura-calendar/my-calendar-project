import calendar
import re
import unicodedata
import streamlit as st

def get_canonical(text):
    """全角半角、空白を統一して比較可能なキーを作る"""
    return unicodedata.normalize('NFKC', str(text)).strip().lower()

def pdf_reader(file_name, df, target_staff):
    """
    名前列の幅で取得された df.iloc[0,0] から
    勤務地と日付を特定し、シフトを抽出する
    """
    # 1. iloc[0,0] の中身を詳細に分解
    cell_text = str(df.iloc[0, 0])
    elements = [e.strip() for e in cell_text.split() if e.strip()]
    
    # 勤務地(辞書キー)の特定ロジック
    # リストの中から「T1」や「T2」、または時程表のA列に該当する文字を探す
    location_key = None
    for item in elements:
        # ここでは T1/T2 などのパターン、または特定のキーワードで判定
        if re.search(r'T[12]', item): 
            location_key = get_canonical(item)
            break
    
    # 2. 勤務地が見つからなければ即座に停止（「金」などを掴むのを防ぐ）
    if not location_key:
        st.error(f"⚠️ 勤務地特定失敗: PDFの左端から有効な場所名が見つかりません。\n取得内容: {elements}")
        st.stop()

    # 3. スタッフのシフト抽出
    clean_target = re.sub(r'[\s　]', '', str(target_staff))
    search_col = df.iloc[:, 0].astype(str).str.replace(r'[\s　]', '', regex=True)
    
    matched_indices = df.index[search_col == clean_target].tolist()
    if not matched_indices:
        st.warning(f"スタッフ '{target_staff}' が見つかりません。")
        return location_key, None, None

    idx = matched_indices[0]
    my_shift = df.iloc[idx : idx+2].copy()
    other_shift = df[(search_col != clean_target) & (df.index != 0)].copy()
    
    return location_key, my_shift, other_shift
