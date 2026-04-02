import streamlit as st
import pandas as pd
import practice_0 as p0
from datetime import datetime
import io

def main():
    st.set_page_config(page_title="勤務シフトCSV出力システム", layout="wide")
    st.title("勤務シフトCSV出力システム")

    # --- サイドバー設定 ---
    st.sidebar.header("1. ユーザー設定")
    target_staff = st.sidebar.text_input("本人の氏名", value="西村文宏")
    target_date = st.sidebar.date_input("解析対象日", datetime(2026, 1, 1))
    
    # PDFの日付列を特定（1日がindex 0または1。スニペットに基づき調整）
    # 通常、日付とdayは連動しますが、PDFの列構造に合わせます
    current_col = target_date.day 

    # --- メインコンテンツ ---
    st.subheader("2. ファイルのアップロード")
    col1, col2 = st.columns(2)
    
    with col1:
        uploaded_pdf = st.file_uploader("勤務表PDFをアップロード", type="pdf")
    
    with col2:
        # 本来はGoogle Drive連携ですが、テスト用に手動アップロードも受け付ける構成
        uploaded_time_sheet = st.file_uploader("時程表(Excel/CSV)をアップロード（任意）", type=["xlsx", "csv"])

    # 模擬的な時程表データの準備（Drive連携がない場合のフォールバック）
    time_dic = {}
    if uploaded_time_sheet:
        # アップロードされたファイルを読み込み（簡易実装）
        try:
            if uploaded_time_sheet.name.endswith('.xlsx'):
                df_time = pd.read_excel(uploaded_time_sheet)
                time_dic["アップロード拠点"] = df_time
            else:
                df_time = pd.read_csv(uploaded_time_sheet)
                time_dic["アップロード拠点"] = df_time
        except Exception as e:
            st.error(f"時程表の読み込みエラー: {e}")

    if uploaded_pdf:
        # 1. PDFから勤務地とスタッフデータを抽出
        pdf_dic = p0.pdf_reader(uploaded_pdf, target_staff)
        
        if pdf_dic:
            st.success(f"PDFから「{target_staff}」に関連する勤務地を {len(pdf_dic)} 件検出しました。")
            
            # 抽出された勤務地のプレビュー
            st.markdown("### 🔍 抽出結果の確認")
            for workplace in pdf_dic.keys():
                st.info(f"検出された勤務地: **{workplace}**")

            # 2. 時程表との統合（紐付け）
            # 本来は p0.time_schedule_from_drive 等で取得した time_dic を使います
            integrated_data = p0.data_integration(pdf_dic, time_dic)
            
            # 3. CSV行の生成
            target_date_str = target_date.strftime("%Y-%m-%d")
            final_rows = p0.process_integrated_data(integrated_data, target_date_str, current_col)
            
            if final_rows:
                # DataFrameに変換
                columns = ["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location"]
                df_final = pd.DataFrame(final_rows, columns=columns)
                
                st.markdown("### 📅 生成されたシフトデータ (プレビュー)")
                st.dataframe(df_final)
                
                # 4. CSVダウンロード
                csv_buffer = io.StringIO()
                df_final.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
                csv_data = csv_buffer.getvalue()
                
                st.download_button(
                    label="月間.csv をダウンロード",
                    data=csv_data,
                    file_name=f"月間_{target_staff}_{target_date_str}.csv",
                    mime="text/csv",
                )
            else:
                st.warning("指定した日付のシフトデータが見つかりませんでした。")
                if not time_dic:
                    st.info("時程表が設定されていないため、詳細な時間計算はスキップされました。")
        else:
            st.error(f"PDF内に「{target_staff}」は見つかりませんでした。")

if __name__ == "__main__":
    main()
