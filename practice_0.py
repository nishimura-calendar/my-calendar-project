import pandas as pd
import pdfplumber
import re
import io
import unicodedata
import streamlit as st

def extract_year_month(pdf_stream):
    """PDFテキストから年月(20XX年XX月)を抽出"""
    try:
        with pdfplumber.open(pdf_stream) as pdf:
            text = pdf.pages[0].extract_text()
            if not text:
                return "2026", "3"
            
            # 正規表現の修正済み
            match = re.search(r'(20\d{2})年\s*(\d{1,2})月', text)
            if match:
                return match.group(1), match.group(2)
            
            # 2026.3 などの形式にも対応
            match_alt = re.search(r'(20\d{2})\.(\d{1,2})', text)
            if match_alt:
                return match_alt.group(1), match_alt.group(2)
                
    except Exception as e:
        st.error(f"年月抽出エラー: {e}")
        
    return "2026", "3"

def parse_special_shift(text):
    """'9@14' や '10.5@19' を解析"""
    text = str(text).strip().replace(' ', '').replace('　', '')
    if "@" in text:
        try:
            parts = text.split("@")
            def conv(val_str):
                v = float(val_str)
                h = int(v)
                m = int(round((v % 1) * 60))
                return f"{h:02d}:{m:02d}"
            return conv(parts[0]), conv(parts[1]), True
        except:
            return "", "", False
    return "", "", False

def data_integration(pdf_dic, time_sched_dic):
    """PDFデータと時程表を場所名(key)で統合"""
    integrated = {}
    
    # デバッグ用：現在持っているキーを表示
    if not pdf_dic:
        st.warning("PDFから表が抽出されていません。")
    if not time_sched_dic:
        st.warning("時程表データが読み込まれていません。")

    for key in pdf_dic.keys():
        # 時程表側のキーを正規化して比較（スペースなどの差異を吸収）
        norm_key = unicodedata.normalize('NFKC', key).strip()
        
        # 時程表の中に一致する場所があるか探す
        match_key = None
        for t_key in time_sched_dic.keys():
            if norm_key in unicodedata.normalize('NFKC', t_key).strip():
                match_key = t_key
                break
        
        if match_key:
            integrated[key] = pdf_dic[key] + [time_sched_dic[match_key]]
        else:
            st.info(f"場所 '{key}' に一致する時程表が見つかりません。")
            
    return integrated

def pdf_reader(pdf_stream, target_staff):
    """pdfplumberを使用して表を読み取り、場所別に整理する"""
    pdf_dic = {}
    clean_target = unicodedata.normalize('NFKC', str(target_staff)).strip()
    
    with pdfplumber.open(pdf_stream) as pdf:
        for i, page in enumerate(pdf.pages):
            tables = page.extract_tables()
            if not tables:
                continue
                
            for j, table in enumerate(tables):
                df = pd.DataFrame(table)
                if df.empty or df.shape[1] < 2:
                    continue
                
                # 場所名の特定（表の左上セルなどを解析）
                first_cell = str(df.iloc[0, 0])
                # 改行があれば最初の行を場所名とする
                loc_name = first_cell.split('\n')[0].strip()
                loc_name = unicodedata.normalize('NFKC', loc_name)
                
                # キーが空、または「場所」などでないか確認
                if not loc_name or "None" in loc_name:
                    loc_name = f"場所_{i+1}"

                # --- 自分の行(my_s)と全員の行(other_s)を特定するロジック ---
                # 西村さんのPDF構造：1つの表に全員分あるか、個人別か
                # ここでは「自分の名前」が含まれる行を探して my_s を作る簡易版
                
                my_rows = []
                for idx, row in df.iterrows():
                    row_str = "".join(row.astype(str))
                    if clean_target in unicodedata.normalize('NFKC', row_str):
                        # 名前が見つかった行とその下の行（備考など）をセットにする
                        my_rows.append(df.iloc[idx : idx+2, :])
                        break # 最初に見つかったものを採用
                
                if my_rows:
                    my_s = my_rows[0].reset_index(drop=True)
                    # pdf_dic[場所名] = [自分のDF, 元のDF]
                    pdf_dic[loc_name] = [my_s, df]
                
    return pdf_dic

def time_schedule_from_drive(service, file_id):
    """Google Driveからの取得（実際はAPIを使用）"""
    # この関数は現状、空またはダミーを返す設計になっています
    # 運用時はここに実際の取得ロジックを入れます
    return {}
