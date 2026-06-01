import pandas as pd
import camelot
import re
import calendar

def get_calc_date_info(y, m):
    """
    【補助関数】
    ファイル名（年月）から算出する論理上の「最終日付（日数）」と「最終曜日」を取得する。
    """
    _, last_day = calendar.monthrange(y, m)
    w_list = ["月", "火", "水", "木", "金", "土", "日"]
    last_w = w_list[calendar.weekday(y, m, last_day)]
    return last_day, last_w


def analyze_pdf_structure(pdf_path, y, m):
    """
    【第1関門 ＆ 第2関門】 pdfシフト表ファイル読込 一体型メインプログラム
    
    手順書 [2]．pdfシフト表ファイル読込 仕様：
      <1>(2) [0,0]から1~月末までの日付、勤務地、曜日を正確に読み込む
      <1>(3) 【第1関門】 計算上の月末日付・曜日(A) と PDF抽出結果(B) を照合
      <2>(1) [0,0]から日付と曜日を除去して勤務地(C)を抽出
      <2>(2) 【第2関門】 時程表の勤務地keyにCが完全一致で存在するか確認
    """
    # 1. camelotを使用してPDFから表データを読み込み
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    if not tables: 
        return None, "PDF表抽出失敗"
    df = tables[0].df
    
    # A：プログラム内部（カレンダー）から計算した最終日付と最終曜日
    calc_last_day, calc_last_w = get_calc_date_info(y, m)
    
    # ----------------------------------------------------
    # 🌟 仕様 <1> (2) ： [0,0] セルからの月末日付・曜日抽出
    # ----------------------------------------------------
    # [0, 0] セルの生文字列を取得（すべてのヘッダー情報が集約されている前提）
    cell_0_0 = str(df.iloc[0, 0]).strip()
    
    # セル内からすべての「数字（1〜31など）」を抽出して数値リスト化
    all_digits = [int(d) for d in re.findall(r'\d+', cell_0_0)]
    # リスト内の最大値（例: 31）を「PDF上の月末日」とする
    pdf_last_day = max(all_digits) if all_digits else 0
    
    # セル内からすべての「曜日（全角の月〜日、およびフォント誤認識の士）」を抽出
    all_weeks = re.findall(r'[月火水木金土日士]', cell_0_0)
    # 抽出されたリストの「最後の文字」（例: 土）を「PDF上の月末曜日」とする
    pdf_last_w = all_weeks[-1] if all_weeks else ""
    
    # PDFフォント特有の誤認識「士」を「土」に自動補正
    if pdf_last_w == "士":
        pdf_last_w = "土"

    # ----------------------------------------------------
    # 🌟 仕様 <1> (3) ： 【第1関門】 データの照合
    # ----------------------------------------------------
    # A（計算上） = B（PDF抽出） の検証
    if not (pdf_last_day == calc_last_day and pdf_last_w == calc_last_w):
        # A≠Bなら理由を添えてプログラムを停止（戻り値でエラーを渡す）
        error_msg = f"不一致：計算上の月末={calc_last_day}日({calc_last_w}) ／ PDF[0,0]から抽出={pdf_last_day}日({pdf_last_w})"
        return None, error_msg

    # ----------------------------------------------------
    # 🌟 仕様 <2> (1) ： 勤務地(C)の純粋抽出
    # ----------------------------------------------------
    # [0,0]から1~月末までの日付（独立した数字）を除去
    location_c = re.sub(r'\b([1-9]|[12][0-9]|3[01])\b', '', cell_0_0)
    # 曜日文字、および前後のカッコ（存在する場合）を除去
    location_c = re.sub(r'\(?[月火水木金土日士]\)?', '', location_c)
    # 残った文字列から「年」「月」「日」「度」や不要な記号・スペース・改行を完全に掃除
    location_c = re.sub(r'[年月日で\s/：:・_ー~～-]', '', location_c).strip()
    
    # ----------------------------------------------------
    # 🌟 仕様 <2> (2) ： 【第2関門】 時程表キーとの完全一致確認
    # ----------------------------------------------------
    # ※ この関数を呼び出す前に、時程表から master_keys（勤務地のリスト）が取得されている想定
    # 例: master_keys = ["T1", "T2", "本町"]
    # ここでは仮のデモ用に、後続で柔軟にチェックできるよう、
    # 実際の完全一致判定ロジックはStreamlit側（app.py）で行うか、
    # またはこの内部で引数として受け取ったマスターと照合させる形にします。
    #（本コードではapp.py側でエラー表示・停止を行いやすいよう、そのまま location_c を返します）

    # ----------------------------------------------------
    # 🌟 後続処理のためのデータ構造化（マトリクス再構築）
    # ----------------------------------------------------
    # Camelotのパースにより[0,0]にデータが集中しているため、
    # 1行目・2行目の列構成を壊さないよう内部用配列（rows）を作成
    rows = []
    rows.append([""] + df.iloc[0, 1:].tolist()) 
    rows.append([location_c] + df.iloc[1, 1:].tolist())
    
    # 3行目以降から各スタッフ名とシフト文字の読み込み
    staff_names = []
    for i in range(2, len(df)):
        cell = str(df.iloc[i, 0]).strip()
        # 偶数行は「名前行」であるため、セル内改行があれば最初の要素（名前）のみを取得
        val = cell.split('\n')[0] if i % 2 == 0 else cell
        rows.append([val] + df.iloc[i, 1:].tolist())
        
        # スタッフ一覧リストを生成（勤務地や会社名、総括などのヘッダーノイズを除外）
        if i % 2 == 0 and val and val != location_c and not re.search(r'警備隊|株式会社|総括|予定表', val):
            staff_names.append(val)
            
    # パースに成功したデータを辞書型にまとめて「通過」ステータスと共に返す
    result_data = {
        "df": pd.DataFrame(rows), 
        "location": location_c, 
        "staff_list": staff_names
    }
    
    return result_data, "通過"
