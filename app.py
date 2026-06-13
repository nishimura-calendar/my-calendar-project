import streamlit as st
import datetime
from practice_0 import generate_shift_csv

# 定数
FOLDER_ID = "19GBObKKJQylZXLaxfApt3iSgA1893TKa"

def main():
    st.title("シフトカレンダー作成システム")
    
    # 1. アップロード処理とPDF解析 (第2関門)
    uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")
    if uploaded_file:
        # ここで勤務地(key)とスタッフ名を特定するロジックを実行
        key = "T1" # 仮定
        staff_name = "山田太郎" # 仮定
        
        # 2. 処理実行
        if st.button("CSV生成と保存"):
            csv_rows = generate_shift_csv(key, staff_name, {}, {}, {})
            
            # 3. 年月_名前_Key.csv で保存
            now = datetime.datetime.now()
            file_name = f"{now.strftime('%Y%m')}_{staff_name}_{key}.csv"
            
            # Google Drive API連携 (保存処理)
            # save_to_drive(csv_rows, file_name, FOLDER_ID)
            
            st.success(f"{file_name} を生成し保存しました。")

if __name__ == "__main__":
    main()
