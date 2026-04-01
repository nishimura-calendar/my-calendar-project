import streamlit as st
import practice_0 as p0
import io
import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build

def get_sheets_service():
    """Google Sheets API サービスを取得"""
    try:
        creds_info = st.secrets["gcp_service_account"]
        credentials = service_account.Credentials.from_service_account_info(
            creds_info,
            scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
        )
        return build('sheets', 'v4', credentials=credentials)
    except Exception as e:
        st.error(f"Google認証に失敗しました。Secretsの設定を確認してください: {e}")
        return None

def main():
    st.set_page_config(page_title="シフト・時程 統合システム", layout="wide")
    
    # サイドバー設定
    st.sidebar.header("設定")
    target_staff = st.sidebar.text_input("検索する氏名", value="田坂 友愛")
    spreadsheet_id = st.sidebar.text_input("スプレッドシートID", value="1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE")
    
    st.title("📅 シフト・時程表 統合管理")
    st.markdown(f"**検索対象:** `{target_staff}` さん")

    # ファイルアップローダー
    pdf_file = st.file_uploader("勤務表PDFをアップロードしてください", type="pdf")

    if pdf_file and target_staff:
        if st.button("解析と紐付けを実行"):
            service = get_sheets_service()
            if not service: return
            
            with st.spinner("データを解析中..."):
                # 1. スプレッドシートから時程表データを取得
                # (A列をキーにした辞書形式: { "T1": {"raw_name": "T1", "df": df}, ... })
                time_dic = p0.time_schedule_from_drive(service, spreadsheet_id)
                
                # 2. PDFから個人シフトを抽出
                pdf_stream = io.BytesIO(pdf_file.read())
                pdf_dic = p0.pdf_reader(pdf_stream, target_staff)

                if not pdf_dic:
                    st.error(f"PDF内に「{target_staff}」さんのデータが見つかりませんでした。")
                    return

                # 3. 紐付け処理
                final_data = p0.data_integration(pdf_dic, time_dic)
                
                if not final_data:
                    st.warning("⚠️ 勤務地の紐付けに失敗しました。")
                    # デバッグ情報の表示
                    with st.expander("紐付け失敗の調査用データ"):
                        st.write("PDFから見つかった勤務地キー:", list(pdf_dic.keys()))
                        st.write("シートから見つかった勤務地キー:", list(time_dic.keys()))
                    return

                # 4. 結果の表示
                st.divider()
                for loc_key, content in final_data.items():
                    my_df = content[0]        # 自分の2行シフト
                    other_df = content[1]     # 同僚のシフト
                    time_sched_df = content[2] # その場所の時程表
                    
                    st.header(f"📍 勤務地: {loc_key}")
                    
                    # タブで表示を切り替え
                    tab1, tab2, tab3 = st.tabs(["📋 自分の今日の予定", "👥 同僚の動き", "⏱ 拠点時程表"])
                    
                    with tab1:
                        st.subheader("あなたのシフト")
                        st.dataframe(my_df, use_container_width=True)
                        
                        st.subheader("この場所の時程（詳細）")
                        st.dataframe(time_sched_df, use_container_width=True)
                        
                        # ダウンロードボタン
                        csv = my_df.to_csv(index=False).encode('utf_8_sig')
                        st.download_button(
                            label=f"{loc_key}のシフトをCSVで保存",
                            data=csv,
                            file_name=f"myshift_{loc_key}.csv",
                            mime='text/csv',
                        )

                    with tab2:
                        st.subheader("同じ勤務地のメンバー")
                        st.dataframe(other_df, use_container_width=True)

                    with tab3:
                        st.subheader(f"{loc_key} 全体のタイムスケジュール")
                        st.table(time_sched_df.iloc[:5, :]) # 冒頭だけ確認用
                        st.write("※ 全データは「自分の今日の予定」タブの下部で確認できます。")

    else:
        st.info("左側のサイドバーで氏名を確認し、PDFファイルをアップロードしてください。")

if __name__ == "__main__":
    main()
