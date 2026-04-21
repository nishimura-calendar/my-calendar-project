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
    with st.spinner(f"{target_staff} さんのデータを解析中..."):
        try:
            # 1. PDFの解析 (practice_0.py の pdf_reader を使用)
            # ※戻り値: pdf_results={勤務地: [my_daily, others]}, year, month
            pdf_results, year, month = p0.pdf_reader(uploaded_pdf, target_staff, uploaded_pdf.name)
            
            if not pdf_results:
                st.error(f"PDF内に「{target_staff}」さんのデータが見つかりませんでした。")
                st.write("ヒント: 名前が正確か、またはPDFのパース形式(格子/ストリーム)が合っているか確認してください。")
                st.stop()

            # 2. 時程表の取得 (本来は Drive から)
            # 現状はデバッグ用に空の辞書またはダミーを想定
            # time_dic = p0.time_schedule_from_drive(service, sheet_id)
            time_dic = {} # ダミー。実際にはDrive連携を有効にします。

            # 3. データの統合
            # integrated = p0.integrate_with_warning(pdf_results, time_dic)
            
            # --- 解析結果の確認画面 ---
            st.success(f"解析完了: {year}年{month}月分")
            
            for place, data in pdf_results.items():
                st.divider()
                st.subheader(f"📍 勤務地: {place}")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write("🟢 **あなたのシフトデータ (my_daily_shift)**")
                    st.dataframe(data[0])
                
                with col2:
                    st.write("👥 **他スタッフのデータ (other_staff_shift)**")
                    st.caption("※自分自身の行や日付ヘッダー行が除外されています。")
                    st.dataframe(data[1])

            # 4. カレンダー行の生成
            # (実際には時程表とのマッピングが必要ですが、ここでは構造の確認まで)
            # final_rows = p0.process_full_month(integrated, year, month)
            
            # ... CSV変換・ダウンロード処理 ...

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
            st.exception(e)

else:
    st.write(f"👉 「{target_staff}」さんとして解析を開始するには、サイドバーのボタンを押してください。")
