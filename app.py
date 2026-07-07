import streamlit as st
import camelot
import re
import calendar
import pandas as pd
import io
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# --- 1. 時程表読み込み (IDを固定) ---
def time_schedule_from_drive(service, file_id="1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"):
    """
    指定IDのスプレッドシートから勤務地Keyと時間行を抽出して辞書化する
    """
    request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    downloader.next_chunk()
    fh.seek(0)
    
    # 形式に従い読み込み
    df = pd.read_excel(fh, header=None, dtype=str).fillna('')
    
    # A列に勤務地(T1, T2等)がある行を特定
    location_rows = df[df.iloc[:, 0].str.strip() != ''].index.tolist()
    location_data_dic = {}
    
    for i, start_row in enumerate(location_rows):
        key = df.iloc[start_row, 0].strip()
        end_row = location_rows[i+1] if i+1 < len(location_rows) else len(df)
        # 範囲内のデータを辞書へ (詳細な時間変換ロジックはここへ追加)
        location_data_dic[key] = df.iloc[start_row:end_row, :]
        
    return location_data_dic

# --- 2. 第1・第2関門突破ロジック ---
def validate_pdf(pdf_path, location_data_dic, target_year, target_month):
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    if not tables:
        st.error("PDF読み込み失敗")
        st.stop()
    df = tables[0].df
    
    # 第1関門: 日付整合性チェック
    all_cells = df.astype(str).values.flatten()
    days = [int(n) for cell in all_cells for n in re.findall(r'\d+', cell) if 1 <= int(n) <= 31]
    max_day_pdf = max(days) if days else 0
    _, last_day = calendar.monthrange(int(target_year), int(target_month))
    
    if max_day_pdf != last_day:
        st.error(f"第1関門失敗: 最終日付が不一致 (PDF:{max_day_pdf}日 vs カレンダー:{last_day}日)")
        st.stop()

    # 第2関門: 勤務地Key完全一致検索
    pdf_first_col = df.iloc[:, 0].astype(str).tolist()
    for key in location_data_dic.keys():
        if not any(key == cell.strip() for cell in pdf_first_col):
            st.error(f"第2関門失敗: 勤務地-{key}-が見当たりません。")
            # PDF表示処理をここに配置
            st.stop()
            
    return True

# --- 3. メイン ---
def main():
    st.title("シフトカレンダー作成")
    # ここにservice生成処理 (st.secrets等から認証情報を取得)
    
    uploaded_file = st.file_uploader("PDFをアップロード", type="pdf")
    if uploaded_file and st.button("解析開始"):
        # 処理実行
        # location_data_dic = time_schedule_from_drive(service)
        # validate_pdf(...)
        st.success("通過しました。詳細解析へ進みます。")

if __name__ == "__main__":
    main()
