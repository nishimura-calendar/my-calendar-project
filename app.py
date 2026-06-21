import streamlit as st
import re
import calendar
import camelot
import os

# --- 第1関門の関数 ---

def get_b_from_pdf(pdf_file_path):
    """B: PDF内容から月末日を特定する（より堅牢な実装）"""
    tables = camelot.read_pdf(pdf_file_path, pages='1', flavor='stream')
    df = tables[0].df
    all_data = df.astype(str).values.flatten()
    
    days = []
    for v in all_data:
        clean_v = v.strip()
        # 数字のみである場合、または「1.0」のような小数点形式の場合に対応
        try:
            # 小数点が含まれていても整数に変換する
            num = int(float(clean_v))
            # カレンダーの日付として妥当な範囲（1〜31）のみ抽出
            if 1 <= num <= 31:
                days.append(num)
        except (ValueError, TypeError):
            continue
            
    return max(days) if days else 0
    
def get_a_from_filename(filename):
    """A: ファイル名から年・月を特定し、その月の最終日を取得する"""
    year_match = re.search(r'20\d{2}', filename)
    month_match = re.search(r'(\d{1,2})月', filename)
    
    if year_match and month_match:
        year = int(year_match.group(0))
        month = int(month_match.group(1))
        _, last_day = calendar.monthrange(year, month)
        return last_day
    return None

def first_gate_check(uploaded_file):
    """第1関門：A=Bの検証"""
    filename = uploaded_file.name
    
    # 1. 一時ファイルとして保存 (Camelotはファイルパスが必要なため)
    temp_path = "temp_shift.pdf"
    with open(temp_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    # 2. B: 内容から取得
    last_day_b = get_b_from_pdf(temp_path)
    
    # 3. A: ファイル名から取得
    last_day_a = get_a_from_filename(filename)
    
    # 4. クリーンアップ
    if os.path.exists(temp_path):
        os.remove(temp_path)
        
    if last_day_a is None:
        return False, "ファイル名から年・月が特定できませんでした。"
    
    if last_day_a != last_day_b:
        return False, f"整合性エラー: ファイル名からは{last_day_a}日までですが、PDF内容からは{last_day_b}日までとなっています。"
    
    return True, f"第1関門突破: {last_day_a}日までのデータとして確認しました。"

# --- メイン処理 ---

def main():
    st.title("シフトカレンダー作成システム")
    uploaded_file = st.file_uploader("読み込むpdfシフトファイルを開いてください。", type="pdf")
    
    if uploaded_file is not None:
        if st.button("実行"):
            with st.spinner("第1関門を通過中..."):
                success, message = first_gate_check(uploaded_file)
                if success:
                    st.success(message)
                    # ここに第2関門への処理を追加予定
                else:
                    st.error(message)

if __name__ == "__main__":
    main()
