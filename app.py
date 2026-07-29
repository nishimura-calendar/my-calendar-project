import pdfplumber
import pandas as pd
import streamlit as st

st.title("人名抽出テスト")
uploaded_pdf = st.file_uploader("PDFをアップロード", type="pdf")

if uploaded_pdf:
    with pdfplumber.open(uploaded_pdf) as pdf:
        page = pdf.pages[0]
        
        # ① アンカーから表の開始位置を整理
        t1_word = next((w for w in page.extract_words() if "T1" in w["text"]), None)
        if not t1_word:
            st.error("T1が見つかりませんでした")
            st.stop()
            
        bbox = (0, t1_word["bottom"], page.width, page.height)
        # テーブル抽出設定を強化（罫線ベースで抽出）
        table = page.crop(bbox).extract_table(table_settings={"vertical_strategy": "lines"})
        df_pdf = pd.DataFrame(table)
        
        # ② 列の役割を整理して特定
        # 以前のコードでは name_col_idx = 2 (date_col_idx 3 - 1) でしたが、
        # PDFのデータを見ると名前が「列2」または「列1」に散らばっているため、
        # 複数の列を候補として探すように変更します
        
        all_staff_names = []
        # 列1と列2の両方をチェックして抽出する
        for col_idx in [1, 2]:
            names = df_pdf.iloc[2:, col_idx].dropna().unique()
            for name in names:
                name = str(name).strip()
                # 名前の長さや文字制限を緩和して抽出
                if len(name) >= 2 and "休" not in name and "0.5" not in name:
                    if name not in all_staff_names:
                        all_staff_names.append(name)
        
        # 結果を表示
        st.write("### 抽出された人名リスト")
        st.write(all_staff_names)
        
        # デバッグ用：テーブル全体を表示
        st.write("### 抽出されたテーブル")
        st.dataframe(df_pdf)
