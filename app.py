import pdfplumber
import streamlit as st
import re

st.title("人名抽出テスト（テキスト直接解析）")
uploaded_pdf = st.file_uploader("PDFをアップロード", type="pdf")

if uploaded_pdf:
    with pdfplumber.open(uploaded_pdf) as pdf:
        page = pdf.pages[0]
        # 1. ページ内のすべてのテキストを取得
        full_text = page.extract_text()
        
        # 2. テキストを行ごとに分割
        lines = full_text.split('\n')
        
        candidates = []
        # 3. 各行から名前っぽいものを探す
        # ここでは「漢字が含まれ、シフトコード(休,J,A...)を含まない」ものを抽出
        for line in lines:
            # シフトや不要な文字が含まれる行はスキップ
            if any(char in line for char in ["休", "A", "B", "C", "D", "E", "F", "G", "H", "J"]):
                continue
            
            # 2〜6文字程度の漢字・かな文字列を探す（名前のパターン）
            # 氏名の間にあるスペースは許容
            match = re.search(r'([^\d\W]{2,6})', line.replace(" ", ""))
            if match:
                name = match.group(1)
                # 勤務予定表など不要な文字列を除外
                if "勤務予定表" not in name and "関空" not in name and "株式会社" not in name:
                    candidates.append(name)

        # 重複を除去
        all_staff_names = sorted(list(set(candidates)))
        
        st.write("### 抽出された人名リスト")
        st.write(all_staff_names)
        
        st.write("### (参考) 取得したテキストの最初の200文字")
        st.write(full_text[:200])
