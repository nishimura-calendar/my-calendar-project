import pandas as pd
import camelot
import io
import re
import pdfplumber
import unicodedata
import calendar
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account

# --- 1. 時間整形関数：数値やシリアル値を「HH:MM」に変換 ---
def format_to_hhmm(val):
    """Excelのシリアル値(0.25等)や数値をHH:MM形式に変換"""
    try:
        if val == "" or pd.isna(val) or str(val).lower() == "nan": 
            return ""
        if isinstance(val, (int, float)):
            num = float(val)
            # 1未満ならシリアル値、1以上ならそのままの時間（h.mm）として処理
            h = int(num * 24 if num < 1 else num)
            m = int(round((num * 24 - h) * 60 if num < 1 else (num - h) * 60))
            return f"{h:02d}:{m:02d}"
        return str(val).strip()
    except:
        return str(val).strip()

# --- 2. Google Drive サービス取得 ---
def get_gdrive_service(secrets):
    """Streamlitのsecretsからサービスアカウント情報を読み取り、Drive APIサービスを構築"""
    creds = service_account.Credentials.from_service_account_info(
        secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build('drive', 'v3', credentials=creds)

# --- 3. 時程表（スプレッドシート）取得関数 ---
def time_schedule_from_drive(service, file_id):
    """
    指定されたスプレッドシートIDをExcel形式でダウンロードし、
    勤務地（A列）をキーとした辞書形式で各ブロックを抽出する。
    """
    try:
        # スプレッドシートをExcel(xlsx)形式でエクスポート
        request = service.files().export_media(
            fileId=file_id, 
            mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        fh.seek(0)
        
        # 最初のシートを読み込み
        full_df = pd.read_excel(fh, header=None, engine='openpyxl')
        
        # --- 列の境界判定 ---
        # 3列目(D列)以降を調べ、時刻として解釈できない文字列が出たらそこまでをデータ範囲とする
        col_limit = len(full_df.columns)
        for i in range(3, len(full_df.columns)):
            val = full_df.iloc[0, i]
            try:
                if pd.isna(val): continue
                float(val)
            except (ValueError, TypeError):
                col_limit = i
                break

        # --- 勤務地ブロックの分割 ---
        # A列(index 0)に値が入っている行がブロックの開始
        location_indices = full_df[full_df.iloc[:, 0].notna()].index.tolist()
        processed_data_parts = {}
        
        if not location_indices:
            # ブロック分けがない場合は全体を一つのUnknownブロックとして扱う
            processed_data_parts["Unknown"] = full_df.iloc[:, 0:col_limit].copy().fillna('')
        else:
            for i, start_row in enumerate(location_indices):
                end_row = location_indices[i+1] if i+1 < len(location_indices) else len(full_df)
                location_name = str(full_df.iloc[start_row, 0]).strip()
                
                # 範囲を切り出して整形
                df_part = full_df.iloc[start_row:end_row, 0:col_limit].copy().reset_index(drop=True)
                
                # 時刻行（最初の行）の数値を HH:MM に変換
                for col in range(3, df_part.shape[1]):
                    df_part.iloc[0, col] = format_to_hhmm(df_part.iloc[0, col])
                
                processed_data_parts[location_name] = df_part.fillna('')

        return processed_data_parts
    except Exception as e:
        print(f"Time Schedule Error: {e}")
        return None

# --- 4. PDF解析関数 ---
def pdf_reader(pdf_stream, target_staff):
    """PDFから指定スタッフの行と、それ以外のスタッフ（交代相手用）の行を抽出"""
    clean_target = re.sub(r'[\s　]', '', str(target_staff))
    
    # camelot用のテンポラリファイル作成
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
        
    tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    table_dictionary = {}
    
    for table in tables:
        df = table.df
        if not df.empty:
            # 勤務地の抽出（セル内の改行位置から中央付近の行を取得するロジックを継承）
            text = str(df.iloc[0, 0])
            lines = text.splitlines()
            target_index = text.count('\n') // 2
            work_place = lines[target_index] if target_index < len(lines) else (lines[-1] if lines else "Unknown")
            
            # 名前検索用の列を作成
            search_col = df.iloc[:, 0].astype(str).str.replace(r'[\s　]', '', regex=True)
            matched_indices = df.index[search_col == clean_target].tolist()
        
            if matched_indices:
                idx = matched_indices[0]
                # [自分の行(2行分), それ以外の行(0行目と自分以外)]
                my_daily_shift = df.iloc[idx : idx+2].copy()
                other_daily_shift = df[(search_col != clean_target) & (df.index != 0)].copy()
                
                table_dictionary[work_place] = [
                    my_daily_shift.reset_index(drop=True),
                    other_daily_shift.reset_index(drop=True)
                ]
    return table_dictionary

# --- 5. データ統合関数 ---
def data_integration(pdf_dic, time_schedule_dic):
    """
    PDFと時程表の勤務地名を紐付け。
    ※「C」を「T2」に読み替える等の救済措置を含む。
    """
    integrated = {}
    logs = []
    
    def normalize(t):
        return unicodedata.normalize('NFKC', str(t)).replace(' ', '').replace('　', '').lower()

    for pdf_loc, pdf_data in pdf_dic.items():
        norm_pdf_loc = normalize(pdf_loc)
        matched_key = None
        
        # 直接一致または部分一致を検索
        for ts_loc in time_schedule_dic.keys():
            if norm_pdf_loc in normalize(ts_loc) or normalize(ts_loc) in norm_pdf_loc:
                matched_key = ts_loc
                break
        
        # 救済：PDFが 'C' なら 時程表の 'T2' を探す
        if not matched_key and norm_pdf_loc == 'c':
            for ts_loc in time_schedule_dic.keys():
                if "t2" in normalize(ts_loc):
                    matched_key = ts_loc
                    break
        
        if matched_key:
            integrated[matched_key] = pdf_data + [time_schedule_dic[matched_key]]
            logs.append({"PDF勤務地": pdf_loc, "時程表側": matched_key, "状態": "✅ 紐付け完了"})
        else:
            logs.append({"PDF勤務地": pdf_loc, "時程表側": "未検出", "状態": "❌ 失敗"})
            
    return integrated, logs

# --- 6. 年月抽出関数 ---
def extract_year_month(pdf_stream):
    """PDFのテキストから年月（2024年4月等）を抽出"""
    with pdfplumber.open(pdf_stream) as pdf:
        full_text = "".join([page.extract_text() or "" for page in pdf.pages])
        match = re.search(r'(\20\d{2})年\s*(\d{1,2})月', full_text)
        if match:
            return int(match.group(1)), int(match.group(2))
    return None, None

# --- 7. メイン処理ループ（月間スケジュール生成） ---
def process_full_month(integrated_dic, year, month):
    """integrated_dic を元にカレンダー用リストを生成"""
    all_final_rows = []
    num_days = calendar.monthrange(year, month)[1]
    
    # 実際の日付処理ロジック（shift_calの呼び出し等）をここに実装
    # 現時点では紐付け確認を優先するため骨組みのみ
    return all_final_rows
