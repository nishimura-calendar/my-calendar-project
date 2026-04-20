import streamlit as st
import shutil
import os
import platform
import io
import pandas as pd
import practice_0 as p0

# Ghostscript確認等は省略（既存のものを維持）
def ensure_ghostscript():
    gs_executable = shutil.which("gs") or shutil.which("gswin64c") or shutil.which("gswin32c")
    return gs_executable

def main():
    st.set_page_config(page_title="勤務スケジュール抽出システム", layout="wide")
    gs_final_path = ensure_ghostscript()
    st.title("🛡️ 免税店シフト解析 (Camelot版)")

    # 基本設定
    target_name = st.text_input("あなたの名前", value="西村 文宏")
    ss_id = st.text_input("時程表スプレッドシートID", value="1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE")

    # ファイルのアップロード
    uploaded_file = st.file_uploader("シフト表（PDF）を選択してください", type="pdf")

    if uploaded_file and target_name:
        pdf_stream = io.BytesIO(uploaded_file.read())
        
        try:
            with st.spinner("PDFを解析中..."):
                # 【修正】uploaded_file.name を第3引数として渡す
                pdf_results, year, month = p0.pdf_reader(pdf_stream, target_name, uploaded_file.name)
            
            if not pdf_results:
                st.error("指定された名前のデータが見つかりませんでした。")
                # デバッグ情報
                if not year or not month:
                    st.info(f"💡 ヒント: ファイル名 '{uploaded_file.name}' から年月を読み取れませんでした。")
                else:
                    st.info(f"💡 ヒント: {year}年{month}月の表は見つかりましたが、'{target_name}' という名前が見つかりません。")
            else:
                st.success(f"✅ 解析完了: {year}年{month}月度")
                # 以降のスプレッドシート処理などは既存のまま
                
        except Exception as e:
            st.error(f"解析中に予期せぬエラーが発生しました: {e}")

if __name__ == "__main__":
    main()
