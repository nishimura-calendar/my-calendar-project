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
    """B: PDF内容から月末日を特定する（安全に抽出する版）"""
    try:
        tables = camelot.read_pdf(pdf_file_path, pages='1', flavor='stream')
        if not tables:
            return 0
        df = tables[0].df
        all_data = df.astype(str).values.flatten()
        
        days = []
        for v in all_data:
            clean_v = v.strip().replace('.0', '')
            # 数字のみか、かつ「01」〜「31」の範囲かを確認
            if clean_v.isdigit():
                num = int(clean_v)
                if 1 <= num <= 31:
                    days.append(num)
        
        return max(days) if days else 0
    except Exception:
        return 0

def check_key_existence(pdf_file_path, time_dic):
    """
    第2関門: PDF内に勤務地Key(time_dicのキー)が完全一致で含まれるか確認する
    """
    tables = camelot.read_pdf(pdf_file_path, pages='1', flavor='stream')
    # 全データを連結して文字列化
    all_text = "".join(tables[0].df.astype(str).values.flatten())
    
    # 時程表の各Keyと完全一致するか検索
    for key in time_dic.keys():
        # 単純な文字列の包含確認
        if key in all_text:
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
