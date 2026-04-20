import streamlit as st
import shutil
import os
import platform
import io
import pandas as pd
import practice_0 as p0

def ensure_ghostscript():
    """Ghostscriptのパスを確認し、環境変数PATHに追加する"""
    gs_executable = shutil.which("gs") or shutil.which("gswin64c") or shutil.which("gswin32c")
    if not gs_executable and platform.system() == "Windows":
        possible_paths = [r"C:\Program Files\gs", r"C:\Program Files\x86\gs"]
        for base in possible_paths:
            if os.path.exists(base):
                try:
                    versions = os.listdir(base)
                    for v in sorted(versions, reverse=True):
                        bin_path = os.path.join(base, v, "bin")
                        if os.path.exists(bin_path):
                            os.environ["PATH"] = bin_path + os.pathsep + os.environ["PATH"]
                            gs_executable = shutil.which("gswin64c") or shutil.which("gswin32c")
                            if gs_executable: return gs_executable
                except: continue
    return gs_executable

def main():
    st.set_page_config(page_title="勤務スケジュール抽出システム", layout="wide")
    gs_final_path = ensure_ghostscript()

    st.title("🛡️ 免税店シフト解析 (Camelot版)")
    st.subheader("📅 勤務スケジュール抽出システム")
    st.markdown("PDFのシフト表からGoogleカレンダー用CSVを自動生成します。")

    if gs_final_path:
        st.sidebar.success(f"✅ Ghostscript 接続済み")
    else:
        st.sidebar.error("❌ Ghostscript未検出")

    st.divider()

    # 1. 基本設定
    st.header("1. 基本設定")
    col1, col2 = st.columns(2)
    with col1:
        target_name = st.text_input("あなたの名前", value="西村 文宏", key="input_name")
    with col2:
        ss_id = st.text_input("時程表スプレッドシートID", value="1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE", key="input_ss_id")

    # 2. ファイルのアップロード
    st.header("2. ファイルのアップロード")
    uploaded_file = st.file_uploader("シフト表（PDF）を選択してください", type="pdf", key="pdf_uploader")

    if uploaded_file and target_name:
        if not gs_final_path:
            st.warning("Ghostscriptが未設定のため、解析を開始できません。")
        else:
            pdf_stream = io.BytesIO(uploaded_file.read())
            
            try:
                with st.spinner("PDFを解析中..."):
                    # PDFから表と年月を抽出
                    pdf_results, year, month = p0.pdf_reader(pdf_stream, target_name)
                
                if not pdf_results:
                    st.error("指定された名前のデータが見つかりませんでした。")
                    # デバッグ機能：見つかった名前の候補を表示するなどのヒント
                    st.info("💡 ヒント: 名前が「名字 名前」のようにスペースを含んでいるか、PDFの表記と一致しているか確認してください。")
                else:
                    st.success(f"✅ 解析完了: {year}年{month}月度")
                    
                    # 3. スプレッドシート連携
                    with st.spinner("スプレッドシートから時程を取得中..."):
                        try:
                            # secretsにgcp_service_accountの設定があることが前提
                            service = p0.get_sheets_service(st.secrets)
                            time_schedule_df = p0.fetch_time_schedule(service, ss_id)
                            
                            if time_schedule_df.empty:
                                st.warning("時程表の取得に失敗しました。スプレッドシートIDまたは権限を確認してください。")
                                return

                            # 勤務地ごとに統合
                            integrated = {}
                            for loc, d in pdf_results.items():
                                integrated[loc] = {
                                    "pdf": d,
                                    "times": time_schedule_df
                                }

                            # 4. CSV用データ作成
                            rows = p0.build_calendar_df(integrated, year, month)
                            
                            if rows:
                                df_result = pd.DataFrame(rows, columns=["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location"])
                                st.subheader("抽出されたスケジュール案")
                                st.dataframe(df_result, use_container_width=True)
                                
                                csv = df_result.to_csv(index=False, encoding="utf_8_sig")
                                st.download_button(
                                    label="📥 Googleカレンダー用CSVをダウンロード",
                                    data=csv,
                                    file_name=f"shift_{year}_{month}_{target_name}.csv",
                                    mime="text/csv",
                                    use_container_width=True
                                )
                            else:
                                st.warning("スケジュール行の生成に失敗しました（該当日のシフトが空の可能性があります）。")
                                
                        except Exception as e:
                            st.error(f"データ統合エラー: {e}")
                            st.exception(e) # 詳細なエラーを表示
                    
            except Exception as e:
                st.error(f"解析エラー: {e}")
                st.exception(e)

if __name__ == "__main__":
    main()
