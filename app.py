import streamlit as st
import shutil
import os
import platform
import io
import practice_0 as p0

def ensure_ghostscript():
    """
    Ghostscriptのパスを確認し、見つからない場合は標準的なインストール先を探索して
    環境変数PATHに追加する関数。
    """
    # 既に認識されているかチェック
    gs_executable = shutil.which("gs") or shutil.which("gswin64c") or shutil.which("gswin32c")
    
    if not gs_executable and platform.system() == "Windows":
        possible_paths = [
            r"C:\Program Files\gs",
            r"C:\Program Files\x86\gs"
        ]
        
        for base in possible_paths:
            if os.path.exists(base):
                try:
                    versions = os.listdir(base)
                    for v in sorted(versions, reverse=True):
                        bin_path = os.path.join(base, v, "bin")
                        if os.path.exists(bin_path):
                            os.environ["PATH"] = bin_path + os.pathsep + os.environ["PATH"]
                            gs_executable = shutil.which("gswin64c") or shutil.which("gswin32c")
                            if gs_executable:
                                return gs_executable
                except:
                    continue
                            
    return gs_executable

def main():
    # --- 1. ページ設定とGhostscript確認 ---
    st.set_page_config(page_title="勤務スケジュール抽出システム", layout="wide")

    # Ghostscript実行確認（サイドバーで静かに報告するように変更し、重複を避ける）
    gs_final_path = ensure_ghostscript()

    # --- 2. メインUI表示 ---
    st.title("🛡️ 免税店シフト解析 (Camelot版)")
    st.subheader("📅 勤務スケジュール抽出システム")
    st.markdown("PDFのシフト表からGoogleカレンダー用CSVを自動生成します。")

    # サイドバーでステータス表示
    if gs_final_path:
        st.sidebar.success(f"✅ Ghostscript 接続済み")
    else:
        st.sidebar.error("❌ Ghostscript未検出")
        with st.expander("⚠️ Ghostscriptが見つかりません。解決策を確認してください"):
            st.markdown("""
            **PC（ローカル）で実行中の場合:**
            1. [Ghostscript公式サイト](https://ghostscript.com/releases/gsdnld.html) からインストーラーをダウンロードして実行。
            2. インストール後、**PCを再起動**してください。
            
            **サーバー（Streamlit Cloud）の場合:**
            - `packages.txt` に `ghostscript` と記載があるか確認。
            """)

    st.divider()

    # 3. 基本設定
    st.header("1. 基本設定")
    col1, col2 = st.columns(2)
    with col1:
        target_name = st.text_input("あなたの名前", value="西村 文宏", key="input_name")
    with col2:
        ss_id = st.text_input("時程表スプレッドシートID", value="1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE", key="input_ss_id")

    # 4. ファイルのアップロード
    st.header("2. ファイルのアップロード")
    uploaded_file = st.file_uploader("シフト表（PDF）を選択してください", type="pdf", key="pdf_uploader")

    if uploaded_file and target_name:
        if not gs_final_path:
            st.warning("Ghostscriptが未設定のため、解析を開始できません。")
        else:
            pdf_stream = io.BytesIO(uploaded_file.read())
            
            try:
                with st.spinner("PDFを解析中... (これには数十秒かかる場合があります)"):
                    # practice_0.py の解析ロジックを呼び出し
                    pdf_results, year, month = p0.pdf_reader(pdf_stream, target_name)
                
                if not pdf_results:
                    st.error("指定された名前のデータが見つかりませんでした。")
                else:
                    st.success(f"解析完了: {year}年{month}月度")
                    
                    # スプレッドシート連携
                    try:
                        service = p0.get_sheets_service(st.secrets)
                        time_map = p0.fetch_time_schedule(service, ss_id)
                        
                        integrated = {loc: {"pdf": d, "times": time_map.get(p0.normalize_text(loc).upper(), [])} 
                                      for loc, d in pdf_results.items()}
                        
                        rows = p0.build_calendar_df(integrated, year, month)
                        
                        if rows:
                            df = pd.DataFrame(rows, columns=["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location"])
                            st.subheader("抽出されたスケジュール案")
                            st.dataframe(df, use_container_width=True)
                            
                            csv = df.to_csv(index=False, encoding="utf_8_sig")
                            st.download_button(
                                label="📥 Googleカレンダー用CSVをダウンロード",
                                data=csv,
                                file_name=f"shift_{year}_{month}_{target_name}.csv",
                                mime="text/csv",
                                use_container_width=True
                            )
                    except Exception as e:
                        st.error(f"スプレッドシート連携エラー: {e}")
                    
            except Exception as e:
                st.error(f"解析エラー: {e}")

if __name__ == "__main__":
    main()
