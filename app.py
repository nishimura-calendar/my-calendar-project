import streamlit as st
import re
import calendar
import camelot
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
    """B: PDF内容から月末日を特定する"""
    tables = camelot.read_pdf(pdf_file_path, pages='1', flavor='stream')
    df = tables[0].df
    all_data = df.astype(str).values.flatten()
    
    days = []
    for v in all_data:
        try:
            num = int(float(v.strip()))
            if 1 <= num <= 31:
                days.append(num)
        except (ValueError, TypeError):
            continue
    return max(days) if days else 0

# --- メイン処理 ---

def main():
    st.title("シフトカレンダー作成システム")
    uploaded_file = st.file_uploader("読み込むpdfシフトファイルを開いてください。", type="pdf")
    
    if uploaded_file is not None:
        # 1. ファイル名から自動取得を試みる
        year_a, month_a = get_year_month_from_filename(uploaded_file.name)
        
        # 2. 自動取得できなかったらフォームを表示
        if year_a is None or month_a is None:
            st.warning("ファイル名から年月が特定できませんでした。対象年月を入力してください。")
            year_a = st.number_input("年", value=2026, step=1)
            month_a = st.number_input("月", value=1, min_value=1, max_value=12)
        else:
            st.write(f"ファイルから年月を認識しました: {year_a}年{month_a}月")

        if st.button("実行"):
            # 一時ファイル保存
            temp_path = "temp_shift.pdf"
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            # 整合性チェック
            _, last_day_a = calendar.monthrange(int(year_a), int(month_a))
            last_day_b = get_b_from_pdf(temp_path)
            
            # クリーンアップ
            if os.path.exists(temp_path):
                os.remove(temp_path)
            
            # 判定ロジッ
            if last_day_a == last_day_b:
                st.success(f"第1関門突破: {year_a}年{month_a}月 ({last_day_a}日) として確認しました。")
            else:
                # エラー理由の表示
                st.error(f"整合性エラー: 入力・ファイル名は{last_day_a}日までですが、PDF内容は{last_day_b}日までです。")
                
                # 理由を補足してPDFを表示
                st.write("---")
                st.write("【エラー理由】: 想定される日数と、PDFから解析された日数に不一致があります。")
                
                # 該当PDFの内容を表示
                try:
                    tables = camelot.read_pdf(temp_path, pages='1', flavor='stream')
                    if len(tables) > 0:
                        st.write("原因特定のためのPDFシフト表データ:")
                        st.dataframe(tables[0].df)
                except Exception as e:
                    st.write("PDFの内容を表示できませんでした。")
                
                # プログラムをここで停止
                st.stop()
if __name__ == "__main__":
    main()
