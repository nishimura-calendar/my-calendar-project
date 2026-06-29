import streamlit as st
import camelot
import re
import calendar
import os

# --- 関数定義 ---

def get_year_month_from_filename(filename):
    """ファイル名から年と月を抽出する"""
    year_match = re.search(r'20\d{2}', filename)
    month_match = re.search(r'(\d{1,2})月', filename)
    year = int(year_match.group(0)) if year_match else None
    month = int(month_match.group(1)) if month_match else None
    return year, month

def get_b_from_pdf(pdf_file_path):
    """
    B: PDFのヘッダー行から『日付(1-31)と曜日』のペアを抽出し、その数をカウントする
    """
    try:
        # streamモードでテーブル読み込み
        tables = camelot.read_pdf(pdf_file_path, pages='1', flavor='stream')
        if not tables: return 0, []
        
        df = tables[0].df
        
        # 最初の数行（ヘッダー行）のみを連結して解析対象とする
        # スタッフ行(人名)が入らないように最初の2-3行程度に絞るのがコツ
        header_text = " ".join(df.iloc[0:3].astype(str).values.flatten())
        
        # 「数字(1-31) ＋ 空白 ＋ 曜日」というパターンを検索
        # 例: "1 木", "10 11 土 日" などに対応
        matches = re.findall(r'(?:1[0-9]|2[0-9]|3[0-1]|[1-9])\s*[日月火水木金土]?', header_text)
        
        # ユニークな日付数（重複を排除したカウント）
        found_days = []
        for m in matches:
            day_num = re.search(r'\d+', m).group()
            found_days.append(int(day_num))
            
        unique_days_count = len(set(found_days))
        return unique_days_count, sorted(list(set(found_days)))
        
    except Exception as e:
        st.error(f"PDF解析エラー: {e}")
        return 0, []

# --- メイン処理 ---

def main():
    st.title("シフトカレンダー作成システム")
    uploaded_file = st.file_uploader("読み込むpdfシフトファイルを開いてください。", type="pdf")
    
    if uploaded_file:
        st.write(f"ファイル名: {uploaded_file.name}")
        year_a, month_a = get_year_month_from_filename(uploaded_file.name)
        
        if year_a is None or month_a is None:
            year_a = st.number_input("年を入力してください", value=2026)
            month_a = st.number_input("月を入力してください", value=1)
        else:
            st.info(f"抽出年月: {year_a}年{month_a}月")

        if st.button("実行"):
            temp_path = "temp_shift.pdf"
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            # A: 期待される末日
            _, last_day_expected = calendar.monthrange(int(year_a), int(month_a))
            
            # B: PDFから取得
            last_day_b, found_days = get_b_from_pdf(temp_path)
            
            # 判定
            if last_day_expected == last_day_b:
                st.success(f"整合性OK！ ({last_day_b}日分を検出)")
            else:
                st.error(f"整合性エラー: 期待される日数 {last_day_expected} に対して、{last_day_b} 日しか検出されませんでした。")
                st.write("検出された日付リスト:", found_days)
            
            if os.path.exists(temp_path):
                os.remove(temp_path)

if __name__ == "__main__":
    main()
