import streamlit as st
import pandas as pd
import re
import unicodedata
import camelot
import os

def normalize_text(text):
    """大文字小文字・スペースを無視するための共通正規化"""
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def clean_strictly(text):
    """
    [0,0]専用クリーニング：
    日付(1-31)と曜日を狙い撃ちで排除し、Keyだけを残す
    """
    if not isinstance(text, str): return ""
    # 1. 独立した数字（日付 1-31）のみを削除
    # \b を使うことで 'T2' の '2' は残し、' 2 ' などの独立した数字だけを消します
    text = re.sub(r'\b([1-9]|[12][0-9]|3[01])\b', '', text)
    # 2. 曜日・記号・改行・空白をすべて排除
    text = re.sub(r'[月火水木金土日()/:：\s　\n]', '', text)
    # 3. 小文字化・スペース除去
    return normalize_text(text)

def convert_num_to_time_str(val):
    """0.25単位を15分間隔の時刻に変換 (核となる計算)"""
    try:
        if isinstance(val, (int, float)) or (isinstance(val, str) and re.match(r'^\d+(\.\d+)?$', val)):
            num = float(val)
            hours = int(num)
            minutes = int(round((num - hours) * 60))
            return f"{hours:02d}:{minutes:02d}"
        return str(val)
    except (ValueError, TypeError):
        return str(val)

def scan_pdf_0_0_only(pdf_stream, time_dic):
    """PDFの[0,0]セルのみを検索・判定する"""
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    try:
        tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice')
        if not tables: return [], pd.DataFrame([{"エラー": "表が見つかりません"}])
        
        # [0,0]セルを取得
        raw_val = str(tables[0].df.iloc[0, 0])
        
        # 指定条件でクリーニング (日付・曜日排除)
        cleaned_val = clean_strictly(raw_val)
        
        found_results = []
        # マスター辞書(time_dic)も normalize_text済みであることを想定
        if cleaned_val in time_dic:
            found_results.append({
                'key': cleaned_val,
                'time_schedule': time_dic[cleaned_val]
            })
            status = f"○ 一致しました ({cleaned_val})"
        else:
            status = f"× 不一致 (抽出結果: '{cleaned_val}')"

        # レポート用データの作成
        report_df = pd.DataFrame([{
            "対象セル": "[0,0]",
            "生データ(抜粋)": raw_val[:50].replace('\n', ' ') + "...",
            "排除後の文字列": cleaned_val,
            "判定": status
        }])
        
        return found_results, report_df

    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")
