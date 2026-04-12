import streamlit as st
import pandas as pd
import io
import practice_0 as p0

def main():
    st.set_page_config(page_title="勤務地・時程表 紐付け確認", layout="wide")
    st.title("📍 勤務地・時程表 紐付け確認ツール")
    st.markdown("""
    このツールは、PDFから抽出したスタッフの勤務地と、Google Drive上のスプレッドシート（時程表）を紐付け、
    正しくデータが取得できているかを確認するためのものです。
    """)

    # --- サイドバー設定 ---
    st.sidebar.header("1. ユーザー設定")
    target_staff = st.sidebar.text_input("対象スタッフ名", value="西村 文宏")
    
    st.sidebar.header("2. ファイル指定")
    # PDFのアップロード
    pdf_file = st.sidebar.file_uploader("勤務表PDFを選択", type="pdf")
    
    # 時程表スプレッドシートID（デフォルトで共有IDを設定）
    default_sheet_id = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"
    sheet_id = st.sidebar.text_input("時程表 Spreadsheet ID", value=default_sheet_id)

    # --- メイン処理 ---
    if target_staff and pdf_file and sheet_id:
        if st.button("紐付けと時程表を確認する"):
            try:
                # 1. Google Drive サービス取得
                service = p0.get_gdrive_service(st.secrets)
                
                # 2. PDF解析 (practice_0.py の pdf_reader を使用)
                with st.spinner("PDFを解析中..."):
                    pdf_stream = io.BytesIO(pdf_file.read())
                    pdf_dic = p0.pdf_reader(pdf_stream, target_staff)
                
                if not pdf_dic:
                    st.error(f"PDFから『{target_staff}』のデータが見つかりませんでした。")
                    return

                # 3. 時程表（スプレッドシート）取得
                with st.spinner("Google Driveから時程表を取得中..."):
                    time_schedule_dic = p0.time_schedule_from_drive(service, sheet_id)
                
                if not time_schedule_dic:
                    st.error("時程表の取得に失敗しました。IDを確認してください。")
                    return

                # 4. データの紐付け
                integrated_dic, logs = p0.data_integration(pdf_dic, time_schedule_dic)

                # --- 表示エリア ---
                st.header("🔗 紐付けステータス")
                
                # 紐付けログの表示
                for log in logs:
                    c1, c2, c3 = st.columns([1, 1, 2])
                    c1.write(f"**PDF:** `{log['PDF勤務地']}`")
                    c2.write(f"**時程表:** `{log['時程表側']}`")
                    if "✅" in log["状態"]:
                        c3.success(log["状態"])
                    else:
                        c3.warning(log["状態"])

                st.divider()

                # 5. 各勤務地の時程表を表示
                st.header("📅 時程表（詳細）")
                if integrated_dic:
                    for loc_key, data in integrated_dic.items():
                        # data = [my_shift_df, other_shift_df, time_schedule_df]
                        time_df = data[2]
                        
                        with st.expander(f"勤務地: {loc_key} の時程表を表示", expanded=True):
                            st.write(f"PDF上の勤務地と紐付いた「{loc_key}」ブロックの時程表データです。")
                            # 表を表示
                            st.dataframe(time_df, use_container_width=True)
                            
                            st.info(f"このブロックには {len(time_df)} 行のシフトパターンが登録されています。")
                else:
                    st.warning("紐付けに成功した勤務地がないため、詳細データは表示できません。")

            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
                st.exception(e)
    else:
        st.info("サイドバーから スタッフ名、PDF、スプレッドシートID を設定してください。")

if __name__ == "__main__":
    main()
