import streamlit as st
import practice_0 as p0
import fitz
import re
import pandas as pd

# ※ shift_calが別ファイル(consideration.pyなど)にある場合は buradan importしてください
# ここでは構造維持のために関数定義だけ置いています
def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    # ここにロジックが入る
    return {"date": target_date, "key": key, "code": shift_info}

def stop_with_pdf(error_text, pdf_path):
    """エラーとPDF画像を表示して停止"""
    st.error(error_text)
    doc = fitz.open(pdf_path)
    pix = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2))
    st.image(pix.tobytes("png"), caption="不一致内容の確認")
    st.stop()

st.title("シフト解析システム")

# 時程表（マスター）の読み込み
if 'time_dic' not in st.session_state:
    # 実際はGCP経由で読み込む (app(18).pyの既存ロジックを使用)
    st.session_state.time_dic = {"第1ターミナル": pd.DataFrame()} 

uploaded_file = st.file_uploader("シフト表PDFをアップロード", type="pdf")

if uploaded_file:
    pdf_path = "temp.pdf"
    with open(pdf_path, "wb") as f:
        f.write(uploaded_file.getvalue())

    # ファイル名から年月抽出
    nums = re.findall(r'\d+', uploaded_file.name)
    y, m = 2026, 1 # デフォルト
    if len(nums) >= 2:
        y, m = int(nums[0]), int(nums[1])
    else:
        st.warning("ファイル名から年月を特定できません。")
        y = st.number_input("年", value=2026)
        m = st.number_input("月", value=1)
        if not st.button("解析実行"): st.stop()

    # 第1・第2関門
    res, msg = p0.analyze_pdf_structure(pdf_path, y, m)
    if res is None:
        stop_with_pdf(msg, pdf_path)
    
    location = res['location']
    if location not in st.session_state.time_dic:
        stop_with_pdf(f"第2関門不通過: 【{location}】は時程表にありません。", pdf_path)

    st.success(f"関門通過: {location}")

    # 第3関門
    target_staff = st.selectbox("スタッフを選択してください", ["該当なし"] + res['staff_list'])
    
    if target_staff != "該当なし":
        shift_data = p0.extract_target_data(res['df'], target_staff, location)
        
        if shift_data:
            # 辞書登録 (仕様通り location をキーに登録)
            st.session_state.final_result = {
                location: {
                    "time_schedule": st.session_state.time_dic[location],
                    "my_daily_shift": shift_data['my_daily_shift'],
                    "other_daily_shift": shift_data['other_daily_shift']
                }
            }
            
            # --- <プログラムのメイン工程> 実行 ---
            with st.spinner("カレンダー算出中..."):
                final_rows = p0.execute_main_process(
                    y, m, location, 
                    st.session_state.final_result, 
                    shift_cal # 関数を渡す
                )
                st.session_state.final_rows = final_rows
            
            st.success("全ての工程が完了しました。")
            st.write(st.session_state.final_rows)
