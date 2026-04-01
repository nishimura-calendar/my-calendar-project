import streamlit as st
import practice_0 as p0
import io
import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build

def get_gdrive_service():
    """SecretsからGoogle Drive APIサービスを取得"""
    creds_info = st.secrets["gcp_service_account"]
    credentials = service_account.Credentials.from_service_account_info(
        creds_info,
        scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
    )
    return build('sheets', 'v4', credentials=credentials)

def main():
    st.set_page_config(page_title="シフト・時程表 統合システム", layout="wide")
    st.title("📅 シフト・時程表 統合管理")

    target_staff = st.sidebar.text_input("検索する氏名", value="田坂 友愛")
    pdf_file = st.file_uploader("勤務表PDFをアップロード", type="pdf")
    
    # 時程表スプレッドシートID (基本事項.docxより)
    spreadsheet_id = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

    if pdf_file and target_staff:
        if st.button("データ解析開始"):
            try:
                service = get_gdrive_service()
                
                with st.spinner("データを取得中..."):
                    # 1. Google Driveから時程表取得
                    time_dic = p0.time_schedule_from_drive(service, spreadsheet_id)
                    
                    # 2. PDF解析
                    pdf_stream = io.BytesIO(pdf_file.read())
                    pdf_dic = p0.pdf_reader(pdf_stream, target_staff)
                    
                    if not pdf_dic:
                        st.error(f"「{target_staff}」が見つかりませんでした。")
                        return

                    # 3. 統合
                    final_data = p0.data_integration(pdf_dic, time_dic)
                    
                    if not final_data:
                        st.warning("勤務地の紐付けができませんでした。")
                        return

                    # 4. 打ち合わせ通りのロジックでスケジュール生成
                    for loc, data in final_data.items():
                        my_shift_df = data[0]
                        time_sched_df = data[2]
                        
                        st.subheader(f"📍 勤務地: {loc}")
                        
                        # スケジュール出力用のリスト
                        schedule_results = []
                        
                        # my_shift_dfの1行目が日付、2行目がシフト値と想定
                        # 0列目は「氏名」、1列目から日付
                        dates = my_shift_df.columns[1:]
                        
                        for date_col in dates:
                            val = str(my_shift_df.iloc[1, my_shift_df.columns.get_loc(date_col)]).strip()
                            target_date = date_col # 本来は日付変換が必要
                            
                            # A. 本町の場合
                            if "本町" in val:
                                # 2段目の関数処理 (改行や / で分割されている想定)
                                parts = val.split('/')
                                start_t = parts[1].strip() if len(parts) > 1 else ""
                                end_t = "" # PDFの構造に応じて取得
                                schedule_results.append({
                                    "Subject": "本町", "Start": target_date, "StartTime": start_t,
                                    "End": target_date, "EndTime": end_t, "AllDay": False
                                })
                            
                            # B. 時程表のB列（巡回区域）に値があるか判定
                            elif val in time_sched_df.iloc[:, 1].values:
                                schedule_results.append({
                                    "Subject": f"{loc} {val}", "Start": target_date, "StartTime": "",
                                    "End": target_date, "EndTime": "", "AllDay": True, "Loc": loc
                                })
                                # その後時程表に沿って処理（打ち合わせ通り）
                                # ※ここでは簡易的に「打ち合わせ通り」のマークを付与
                                schedule_results.append({
                                    "Subject": "打ち合わせ通り", "Start": target_date, "StartTime": "打ち合わせ通り",
                                    "End": target_date, "EndTime": "打ち合わせ通り", "AllDay": False
                                })
                                
                            # C. それ以外
                            else:
                                if val:
                                    schedule_results.append({
                                        "Subject": val, "Start": target_date, "StartTime": "",
                                        "End": target_date, "EndTime": "", "AllDay": True
                                    })

                        # 結果表示
                        res_df = pd.DataFrame(schedule_results)
                        st.write("📋 生成されたスケジュール")
                        st.dataframe(res_df)
                        
                        csv = res_df.to_csv(index=False).encode('utf_8_sig')
                        st.download_button(f"CSV保存({loc})", csv, f"schedule_{loc}.csv", "text/csv")

            except Exception as e:
                st.error(f"エラーが発生しました: {e}")

if __name__ == "__main__":
    main()
