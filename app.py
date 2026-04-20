import streamlit as st
import pandas as pd
import io
import practice_0 as p0
import datetime
import calendar
import pdfplumber
import streamlit as st
import shutil
import os
import platform

def ensure_ghostscript():
    """
    Ghostscriptのパスを確認し、見つからない場合は標準的なインストール先を探索して
    環境変数PATHに追加する関数。
    """
    # 既に認識されているかチェック
    gs_executable = shutil.which("gs") or shutil.which("gswin64c") or shutil.which("gswin32c")
    
    if not gs_executable and platform.system() == "Windows":
        # Windowsの場合、標準的なインストール先をいくつか探索
        possible_paths = [
            r"C:\Program Files\gs",
            r"C:\Program Files (x86)\gs"
        ]
        
        for base in possible_paths:
            if os.path.exists(base):
                # gs10.03.1 などのバージョン名フォルダを探す
                versions = os.listdir(base)
                for v in sorted(versions, reverse=True): # 最新バージョンを優先
                    bin_path = os.path.join(base, v, "bin")
                    if os.path.exists(bin_path):
                        # 見つかったbinフォルダをPATHの先頭に追加
                        os.environ["PATH"] = bin_path + os.pathsep + os.environ["PATH"]
                        gs_executable = shutil.which("gswin64c") or shutil.which("gswin32c")
                        if gs_executable:
                            return gs_executable
                            
    return gs_executable

# --- 実行確認 ---
st.set_page_config(page_title="シフト解析システム", layout="wide")

gs_final_path = ensure_ghostscript()

if gs_final_path:
    st.success(f"✅ Ghostscriptを認識しました: {gs_final_path}")
else:
    st.error("❌ Ghostscriptがまだ見つかりません。")
    st.info("【解決策】PCで実行中の場合、Ghostscriptをインストールし、PCを再起動してから再度お試しください。サーバー(Streamlit Cloud)の場合は packages.txt が正しいか確認してください。")

# --- 以降、メインのアプリ処理 ---
st.title("🛡️ 免税店シフト解析 (Camelot版)")
# target_name = st.text_input(...) などのコードが続く
def main():
    st.set_page_config(page_title="勤務スケジュール抽出", layout="centered")
    
    if 'staff_name' not in st.session_state: 
        st.session_state.staff_name = "西村 文宏"

    st.title("📅 勤務スケジュール抽出システム")
    st.markdown("PDFのシフト表からGoogleカレンダー用CSVを自動生成します。")

    st.subheader("1. 基本設定")
    col_name, col_sheet = st.columns([1, 1])
    with col_name:
        target_staff = st.text_input("あなたの名前", value=st.session_state.staff_name)
        st.session_state.staff_name = target_staff
    with col_sheet:
        sheet_id = st.text_input("時程表スプレッドシートID", value="1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE")

    st.subheader("2. ファイルのアップロード")
    pdf_file = st.file_uploader("シフト表（PDF）を選択してください", type="pdf")

    if pdf_file:
        # ファイル読み込み
        pdf_file.seek(0)
        pdf_bytes = pdf_file.read()
        pdf_stream = io.BytesIO(pdf_bytes)
        
        # 1. ファイル名から年月を抽出（改善版ロジック）
        apply_y, apply_m = p0.extract_year_month_from_text(pdf_file.name)
        
        if apply_y and apply_m:
            # 2. 整合性チェック
            mismatch_reasons = []
            
            with st.spinner("PDFの整合性を自動検証中..."):
                # (A) 月末日のチェック
                expected_days = calendar.monthrange(apply_y, apply_m)[1]
                actual_max_day = p0.extract_max_day_from_pdf(pdf_stream)
                if actual_max_day and actual_max_day != expected_days:
                    mismatch_reasons.append(f"日数の不一致: {apply_m}月は{expected_days}日までですが、PDFは{actual_max_day}日まであります。")
                
                # (B) 1日の曜日のチェック
                first_day_date = datetime.date(apply_y, apply_m, 1)
                wd_list = ["月", "火", "水", "木", "金", "土", "日"]
                expected_wd = wd_list[first_day_date.weekday()]
                actual_wd = p0.extract_first_weekday_from_pdf(pdf_stream)
                if actual_wd and actual_wd != expected_wd:
                    mismatch_reasons.append(f"曜日の不一致: {apply_y}年{apply_m}月1日は({expected_wd})曜日ですが、PDFは({actual_wd})曜日となっています。")

            # --- 条件分岐 ---
            if mismatch_reasons:
                # 【相違がある場合】 エラー表示して停止
                st.error("⚠️ ファイル名とPDFの内容に相違が見つかりました")
                for reason in mismatch_reasons:
                    st.write(f"- {reason}")
                
                st.markdown("---")
                st.subheader("📝 アップロードされたPDFの確認")
                try:
                    pdf_stream.seek(0)
                    with pdfplumber.open(pdf_stream) as pdf:
                        if len(pdf.pages) > 0:
                            img = pdf.pages[0].to_image(resolution=150)
                            st.image(img.original, use_container_width=True, caption=f"プレビュー: {pdf_file.name}")
                except Exception as e:
                    st.error(f"プレビュー表示失敗: {e}")
                
                st.warning("内容を確認し、正しいファイルを再アップロードしてください。")

            else:
                # 【相違がない場合】 自動的にカレンダー生成へ進む
                st.success(f"✅ 整合性確認OK: {apply_y}年{apply_m}月の解析を自動開始します。")
                
                try:
                    service = p0.get_gdrive_service(st.secrets)
                    with st.spinner(f"{apply_y}年{apply_m}月のシフトを解析中..."):
                        time_dic = p0.time_schedule_from_drive(service, sheet_id)
                        pdf_stream.seek(0)
                        pdf_dic = p0.pdf_reader(pdf_stream, target_staff)
                        
                        if not pdf_dic:
                            st.error(f"PDF内に『{target_staff}』が見つかりませんでした。")
                        else:
                            integrated_dic, _ = p0.data_integration(pdf_dic, time_dic)
                            final_rows = p0.process_full_month(integrated_dic, int(apply_y), int(apply_m))

                            if final_rows:
                                st.subheader("3. 生成結果（CSV）")
                                df_res = pd.DataFrame(final_rows, columns=["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location"])
                                st.dataframe(df_res, use_container_width=True)
                                
                                csv_buffer = io.StringIO()
                                df_res.to_csv(csv_buffer, index=False, encoding="utf_8_sig")
                                st.download_button(
                                    label="📥 カレンダー用CSVをダウンロード",
                                    data=csv_buffer.getvalue(),
                                    file_name=f"schedule_{apply_y}{apply_m:02d}_{target_staff}.csv",
                                    mime="text/csv",
                                    use_container_width=True,
                                    type="primary"
                                )
                            else:
                                st.warning("該当する勤務データが生成されませんでした。")
                except Exception as e:
                    st.error(f"解析中にエラーが発生しました: {e}")
        else:
            st.error(f"ファイル名『{pdf_file.name}』から年月を特定できません。")

if __name__ == "__main__":
    main()
