import streamlit as st
import camelot
import re
import calendar
import os

def extract_year_month_from_filename(filename):
    """ファイル名から年月を自動抽出"""
    year_match = re.search(r'20\d{2}', filename)
    month_match = re.search(r'(\d{1,2})月', filename)
    if year_match and month_match:
        return int(year_match.group(0)), int(month_match.group(1))
    return None, None

def check_pdf_robustly(pdf_path, year, month):
    try:
        tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
        full_text = " ".join([cell for table in tables for row in table.df.values for cell in row])
        
        # 1. 理論上の末日を特定
        _, last_day = calendar.monthrange(year, month)
        
        # 2. 末日と曜日の行を特定（latticeで取れた表の中から、末日が含まれる行を探す）
        # 31と土が同じ行にあることを重視し、誤検知を防ぐため最後に一致したものを採用
        pattern = fr'{last_day}[\s\S]*?([日月火水木金土])'
        matches = re.findall(pattern, full_text)
        
        if not matches:
            return False, f"末日 {last_day} 日と対応する曜日が特定できませんでした。", None
        
        # 最後のマッチを採用（表の末尾にあるものを優先）
        found_wd = matches[-1]
        
        # 3. 理論値と比較
        theory_wd_idx = calendar.weekday(year, month, last_day)
        jp_weekdays = ["月", "火", "水", "木", "金", "土", "日"]
        
        if found_wd != jp_weekdays[theory_wd_idx]:
            return False, f"不一致: 抽出された{last_day}日は{found_wd}曜日ですが、理論上は{jp_weekdays[theory_wd_idx]}曜日です。", None
            
        return True, f"成功: {year}年{month}月の末日{last_day}日は{found_wd}曜日で整合性OKです。", None
    except Exception as e:
        return False, f"解析エラー: {e}", None

def main():
    st.title("シフトカレンダー作成システム")
    uploaded_file = st.file_uploader("PDFシフト表をアップロードしてください", type="pdf")
    
    if uploaded_file is not None:
        # 1. 自動抽出を試みる
        auto_year, auto_month = extract_year_month_from_filename(uploaded_file.name)
        
        # 2. 未入力（または抽出失敗）の場合のみ入力を求める
        if auto_year is None or auto_month is None:
            st.warning("ファイル名から年月を自動判定できませんでした。年月を入力してください。")
            year = st.number_input("年", value=2026)
            month = st.number_input("月", value=1)
        else:
            st.info(f"自動判定: {auto_year}年 {auto_month}月")
            year, month = auto_year, auto_month
            
        if st.button("シフト表を解析する"):
            temp_path = "temp.pdf"
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            is_success, msg, _ = check_pdf_robustly(temp_path, year, month)
            if is_success:
                st.success(msg)
            else:
                st.error(msg)
            if os.path.exists(temp_path):
                os.remove(temp_path)

if __name__ == "__main__":
    main()
