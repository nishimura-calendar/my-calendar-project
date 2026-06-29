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
    days = [int(float(v.strip())) for v in all_data if v.strip().replace('.0','').isdigit() and 1 <= int(float(v.strip())) <= 31]
    return max(days) if days else 0

def check_key_existence(pdf_file_path, time_dic):
    """
    第2関門1: PDFヘッダーにて[日付]...[Key]...[曜日] の並びを確認する
    """
    tables = camelot.read_pdf(pdf_file_path, pages='1', flavor='stream')
    header_str = "".join(tables[0].df.iloc[0].astype(str).tolist())
    
    for key in time_dic.keys():
        # 正規表現: 数字(日付) + 任意の文字 + Key(完全一致) + 任意の文字 + 曜日(日〜土)
        pattern = rf"\d+.*{re.escape(key)}.*[日月火水木金土]"
        if re.search(pattern, header_str):
            return True, key
    return False, None

# --- メイン処理 ---

def main():
    st.title("シフトカレンダー作成システム")
    uploaded_file = st.file_uploader("読み込むpdfシフトファイルを開いてください。", type="pdf")
    
    # 仮のtime_dic (本来はGoogle Sheetsから読み込んだものを使用)
    time_dic = {"T1": "09:00", "T2": "10:00"} 

    if uploaded_file is not None:
        year_a, month_a = get_year_month_from_filename(uploaded_file.name)
        
        if year_a is None:
            year_a = st.number_input("年", value=2026)
            month_a = st.number_input("月", value=1)

        if st.button("実行"):
            temp_path = "temp_shift.pdf"
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            # 第1関門
            _, last_day_a = calendar.monthrange(int(year_a), int(month_a))
            if last_day_a != get_b_from_pdf(temp_path):
                st.error("第1関門エラー: 日付整合性が取れません。")
            else:
                st.success("第1関門突破！")
                
                # 第2関門
                success, key = check_key_existence(temp_path, time_dic)
                if success:
                    st.success(f"第2関門突破: 勤務地Key [{key}] をヘッダー内で確認しました。")
                else:
                    st.error("第2関門エラー: ヘッダーに勤務地Keyが見当たりません。")
            
            if os.path.exists(temp_path):
                os.remove(temp_path)

if __name__ == "__main__":
    main()
