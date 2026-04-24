import pandas as pd
import camelot
import re
import unicodedata
import streamlit as st

def extract_year_month_from_text(text):
    text = unicodedata.normalize('NFKC', text)
    y_match = re.search(r'(\d{4})年', text)
    m_match = re.search(r'\((\d{1,2})\)', text)
    if not m_match: m_match = re.search(r'(\d{1,2})月', text)
    y_val = int(y_match.group(1)) if y_match else 2026
    m_val = int(m_match.group(1)) if m_match else None
    return y_val, m_val

def pdf_reader_engine(uploaded_pdf, l_boundary):
    with open("temp.pdf", "wb") as f:
        f.write(uploaded_pdf.getbuffer())
    
    # 全体を一つのテキストブロックとして読み取るため、row_tolを大きく設定
    tables = camelot.read_pdf(
        "temp.pdf", pages='1', flavor='stream',
        columns=[str(l_boundary)], 
        row_tol=15, 
        strip_text='\n'
    )
    if not tables: return None
    df_raw = tables[0].df

    # --- 【再構築アルゴリズム】 ---
    # 1. 0列目から「勤務地」と「氏名」を探し、それ以外を「表題エリア」とする
    col0_full_text = "".join(df_raw.iloc[:, 0].astype(str))
    detected_loc = "T2" if "T2" in col0_text_blob(df_raw) else "不明"
    
    # 2. 0行目付近の混濁文字列から「日付」と「曜日」を分離抽出
    mixed_text = "".join(df_raw.iloc[0, :].astype(str))
    
    # 正規表現で「1〜31」の並びを抽出
    days = re.findall(r'(?<!\d)(?:[1-9]|[12]\d|3[01])(?!\d)', mixed_text)
    # 重複や「2026」の断片を除くため、1から始まる連続性をチェック
    clean_days = []
    for d in days:
        if int(d) == len(clean_days) + 1:
            clean_days.append(d)

    # 曜日の抽出（月〜日）
    weekdays = re.findall(r'[月火水木金土日]', mixed_text)

    # 3. 新しい綺麗なDataFrameを作成 (32列：0列目が属性、1〜31列目が日付)
    new_df = pd.DataFrame(columns=range(32))
    
    # 0行目：日付をセット
    date_row = [""] * 32
    for i, d in enumerate(clean_days):
        if i+1 < 32: date_row[i+1] = d
    new_df.loc[0] = date_row

    # 1行目：0列目に勤務地、1列目以降に曜日をセット
    weekday_row = [""] * 32
    weekday_row[0] = detected_loc
    for i, w in enumerate(weekdays):
        if i+1 < 32: weekday_row[i+1] = w
    new_df.loc[1] = weekday_row

    # 2行目以降：スタッフのシフトデータをスキャンして追加
    # 元のdf_rawから名前を探し、その横にあるデータを新しいdfの同じ列位置に流し込む
    for i in range(len(df_raw)):
        row_head = str(df_raw.iloc[i, 0])
        if len(row_head) >= 2 and not any(x in row_head for x in ["2026", "予定表", "T2"]):
            staff_shift_row = [row_head] + [""] * 31
            # 元の行にあるシフト記号（A, B, C等）を抽出して配置（簡易実装）
            # ここは実際のPDFの列のズレに合わせて調整が必要
            new_df.loc[len(new_df)] = staff_shift_row

    return new_df

def col0_text_blob(df):
    return "".join(df.iloc[:, 0].astype(str))

def get_actual_info(df, sheet_id):
    # 再構築後のdfから末日を取得（0行目の最後の非空欄）
    row0 = df.iloc[0, 1:]
    actual_days = [int(x) for x in row0 if str(x).isdigit()]
    return max(actual_days) if actual_days else 0, df.iloc[1, 0]
