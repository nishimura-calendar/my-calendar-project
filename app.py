import streamlit as st
import camelot
import re
import calendar
import os

def extract_year_month_from_filename(filename):
    """ファイル名から「2026年1月」のような年月を正確に抽出"""
    # 年: 2026などの4桁数字
    year_match = re.search(r'20\d{2}', filename)
    # 月: 1月〜12月
    month_match = re.search(r'(\d{1,2})月', filename)
    
    if year_match and month_match:
        return int(year_match.group(0)), int(month_match.group(1))
    return None, None

def check_pdf_robustly(pdf_path, year, month):
    try:
        # 罫線を基準にテーブルを分解
        tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
        
        # 理論上の末日を計算（カレンダーの正当性担保）
        _, last_day = calendar.monthrange(year, month)
        
        # 曜日リスト
        jp_weekdays = ["月", "火", "水", "木", "金", "土", "日"]
        expected_wd = jp_weekdays[calendar.weekday(year, month, last_day)]
        
        # 各テーブル・各行を走査して末日の曜日を探す
        found_wd = None
        for table in tables:
            for i in range(len(table.df)):
                row_text = " ".join([str(cell) for cell in table.df.iloc[i]])
                # 「31」という数字と「その月の最終日の曜日（例：土）」が含まれる行を探す
                # 誤判定を防ぐため、末日の行であることを明確にする
                if str(last_day) in row_text and expected_wd in row_text:
                    found_wd = expected_wd
                    break
            if found_wd: break
            
        if not found_wd:
            return False, f"抽出失敗: {last_day}日（{expected_wd}曜日）の行が正しく見つかりませんでした。", None
            
        return True, f"成功: {year}年{month}月の末日{last_day}日は{found_wd}曜日で整合性OKです。", None
    except Exception as e:
        return False, f"解析エラー: {e}", None

def main():
    st.title("シフトカレンダー作成システム")
    uploaded_file = st.file_uploader("PDFシフト表をアップロードしてください", type="pdf")
    
    if uploaded_file is not None:
        # 1. 自動判定を試行
        f_year, f_month = extract_year_month_from_filename(uploaded_file.name)
        
        # 2. 自動判定できない場合のみ入力フォームを表示
        if f_year is None or f_month is None:
            st.warning("ファイル名から年月を自動判定できませんでした。")
            year = st.number_input("年", value=2026)
            month = st.number_input("月", value=1)
        else:
            st.info(f"ファイル名から判定: {f_year}年 {f_month}月")
            year, month = f_year, f_month
            
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
