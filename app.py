import streamlit as st
import practice_0 as p0
import fitz
import re
import pandas as pd

def stop_with_pdf(error_text, pdf_path):
    """不通過時にエラーと画像を表示して停止"""
    st.error(error_text)
    try:
        doc = fitz.open(pdf_path)
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        st.image(pix.tobytes("png"), caption="不一致内容の確認")
    except:
        st.warning("PDFのプレビュー表示に失敗しました。")
    st.stop()

# 計算用ロジック（実際は別ファイルから読み込む想定）
def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    return {"日付": target_date, "キー": key, "シフト": shift_info}

st.title("シフト解析システム")

if 'time_dic' not in st.session_state:
    # ここにGCP読み込みロジックが入る
    st.session_state.time_dic = {"第1ターミナル": pd.DataFrame()}

uploaded_file = st.file_uploader("免税店シフト表 (PDF)", type="pdf")

if uploaded_file:
    pdf_path = "temp.pdf"
    with open(pdf_path, "wb") as f:
        f.write(uploaded_file.getvalue())

    # 年月抽出
    nums = re.findall(r'\d+', uploaded_file.name)
    y, m = None, None
    for n in nums:
        v = int(n)
        if 2000 <= v <= 2100: y = v
        elif 1 <= v <= 12: m = v

    if not y or not m:
        st.warning("年月を特定できません。入力してください。")
        col1, col2 = st.columns(2)
        y = col1.number_input("年", value=2026)
        m = col2.number_input("月", value=1)
        if not st.button("解析開始"): st.stop()

    # 第1・第2関門
    res, msg = p0.analyze_pdf_structure(pdf_path, y, m)
    if res is None:
        stop_with_pdf(msg, pdf_path)
    
    location = res['location']
    if location not in st.session_state.time_dic:
        stop_with_pdf(f"第2関門不通過: 【{location}】は時程表にありません。", pdf_path)

    st.success(f"関門通過: {location}")

    # 第3関門
    target_staff = st.selectbox("スタッフを選択してください", options=["該当なし"] + res['staff_list'])
    
    if target_staff != "該当なし":
        shift_data = p0.extract_target_data(res['df'], target_staff, location)
        
        if shift_data:
            st.session_state.final_result = {
                location: {
                    "time_schedule": st.session_state.time_dic[location],
                    "my_daily_shift": shift_data['my_daily_shift'],
                    "other_daily_shift": shift_data['other_daily_shift']
                }
            }
            
            with st.spinner("メイン工程実行中..."):
                final_rows = p0.execute_main_process(
                    y, m, location, 
                    st.session_state.final_result, 
                    shift_cal
                )
                st.session_state.final_rows = final_rows
            
            st.write("#### 最終結果")
            st.write(st.session_state.final_rows)
