import pandas as pd
import io
import requests

def load_master_from_sheets():
    """
    [1] 時程表読込
    スプレッドシートを直接読み込み、A列をキーにして辞書化する。
    画面表示は一切行わない。
    """
    # スプレッドシートのID
    sheet_id = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"
    # CSV形式でダウンロードするためのURL
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        
        # CSVデータをデータフレームに読み込む
        df = pd.read_csv(io.StringIO(response.text))
        
        time_dic = {}
        # A列(iloc[:, 0])を勤務地としてグループ化して辞書に格納
        for location, group in df.groupby(df.iloc[:, 0]):
            if pd.notna(location): # 空のキーを除外
                time_dic[str(location).strip()] = group
                
        return time_dic
        
    except Exception as e:
        # 読み込み失敗時は空の辞書を返す等の処理
        return {}
