import streamlit as st
import practice_0 as p0
import pandas as pd
import io
import os

# --- 1. サービスアカウント認証・Drive連携設定 ---
# (実際には secrets.toml から取得)
# service = p0.get_gdrive_service(st.secrets)
# sheet_id = "YOUR_SPREADSHEET_ID"

st.set_page_config(page_title="シフト解析・カレンダー生成", layout="wide")

st.title("📅 個別シフトカレンダー生成")
st.markdown("""
PDFのシフト予定表から、**あなたの名前**のデータを探し出し、
時程表と組み合わせてGoogleカレンダー用のCSVを作成します。
""")

# サイドバー：設定
with st.sidebar:
    st.header("設定")
    # ユーザーが自分の名前を入力
    target_staff = st.text_input("1. 解析する名前を入力", placeholder="例: 西村 文宏")
    st.caption("※名字と名前の間のスペースは自動で詰められます。")

    # PDFアップロード
    uploaded_pdf = st.file_uploader("2. PDFをアップロード", type="pdf")

if not target_staff:
    st.info("左側のサイドバーに「解析する名前」を入力してください。")
    st.stop()

if not uploaded_pdf:
    st.warning("左側のサイドバーから「シフト表PDF」をアップロードしてください。")
    st.stop()

# --- 解析開始 ---
if st.sidebar.button("解析実行"):
    # PDFファイル情報の表示
    st.write(f"📁 **解析対象ファイル:** `{uploaded_pdf.name}` ({uploaded_pdf.size / 1024:.1f} KB)")
    
    with st.spinner(f"{target_staff} さんのデータを解析中..."):
        try:
            # 1. PDFの解析 (practice_0.py の pdf_reader を使用)
            # ※戻り値: pdf_results={勤務地: [my_daily, others]}, year, month
            pdf_results, year, month = p0.pdf_reader(uploaded_pdf, target_staff, uploaded_pdf.name)
            
            # --- 不一致時の理由表示 ---
            if not pdf_results:
                st.error(f"❌ 「{target_staff}」さんのデータが見つかりませんでした。")
                
                with st.expander("🔍 不一致の可能性がある理由を確認する"):
                    st.markdown(f"""
                    1. **名前の表記ゆれ**:
                        - 入力された名前: `{target_staff}`
                        - PDF内では「名字と名前の間にスペースがある」「全角・半角が異なる」などの違いがあるかもしれません。
                        - ※システムは自動でスペースを除去して比較していますが、漢字の間違い（例：斎藤と斉藤）は検知できません。
                    2. **PDFの構造（パース失敗）**:
                        - PDFの作成元ソフトによっては、文字が画像として認識されていたり、文字の間に見えない特殊な改行が含まれている場合があります。
                    3. **勤務地の未検出**:
                        - 表の中に「T1」や「T2」といった勤務地を示すキーワードが見当たらない場合、スキップされることがあります。
                    """)
                st.stop()

            # 2. 時程表の取得 (本来は Drive から)
            # 現状はデバッグ用に空の辞書
            time_dic = {} 

            # --- 解析結果の確認画面 ---
            st.success(f"✅ 解析完了: {year}年{month}月分")
            
            for place, data in pdf_results.items():
                st.divider()
                st.subheader(f"📍 勤務地: {place}")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write("🟢 **あなたのシフトデータ (my_daily_shift)**")
                    st.caption("PDFから抽出されたあなたの2行分のデータです。")
                    st.dataframe(data[0], use_container_width=True)
                
                with col2:
                    st.write("👥 **他スタッフのデータ (other_staff_shift)**")
                    st.caption("交代相手を特定するための参照データです（自分とヘッダーは除外済み）。")
                    st.dataframe(data[1], use_container_width=True)

            # 4. カレンダー行の生成 (処理が実装されている場合)
            # integrated = p0.integrate_with_warning(pdf_results, time_dic)
            # final_rows = p0.process_full_month(integrated, year, month)
            
        except Exception as e:
            st.error(f"⚠️ 解析中に予期せぬエラーが発生しました: {e}")
            st.exception(e)

else:
    st.info(f"💡 「{target_staff}」さんのシフトを抽出するには「解析実行」ボタンを押してください。")
