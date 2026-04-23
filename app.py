import streamlit as st
import practice_0 as p0
import camelot
import os

st.set_page_config(layout="wide")
st.title("📅 シフト・時程表 統合システム")

uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")
target_staff = st.text_input("検索する氏名", value="四村 和義")

if uploaded_file and st.button("解析実行"):
    with open("temp.pdf", "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    # --- 境界線の計算 ---
    # 日本語1文字15pt + マージン
    name_width = len(target_staff) * 15 + 20
    location_width = 60 
    column_boundary = max(name_width, location_width)
    
    # 飲み込み防止の上限
    if column_boundary > 90:
        column_boundary = 90

    try:
        # ご提案の「途中から」を反映
        # table_areasで「名前の右端」から「ページの右端」までを切り出す
        # ※座標はPDFにより微調整が必要ですが、ここでは論理的な範囲を指定
        tables = camelot.read_pdf(
            "temp.pdf", 
            pages='1', 
            flavor='stream', 
            table_areas=[f'{column_boundary},700,595,100'], # [左, 上, 右, 下]
            row_tol=2,     # 文字高さに絞る
            strip_text='\n' # 不要な改行を掃除
        )
        
        if not tables or len(tables) == 0:
            st.error("指定した範囲に表が見つかりませんでした。")
        else:
            # A1セル([0,0])に勤務地が入った状態で解析エンジンへ
            p0.pdf_reader(uploaded_file.name, tables[0].df, target_staff)
            
    except Exception as e:
        st.error(f"解析エラー: {e}")
