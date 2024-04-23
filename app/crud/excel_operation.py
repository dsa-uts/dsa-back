import pandas as pd


def read_excel(filepath):
    # Excelファイルをヘッダー行のみを読み込む
    df_header = pd.read_excel(filepath, header=None, nrows=6, engine="openpyxl")

    # 6行目（英語ヘッダー）を取得
    english_headers = df_header.iloc[5].tolist()

    # 不足しているヘッダー部分を補完
    missing_headers = ["submission", "submission_date", "submission_count", "folder"]
    english_headers.extend(missing_headers)  # 英語ヘッダーに追加

    # NaNのヘッダーを削除
    english_headers = [x for x in english_headers if str(x) != "nan"]

    # 実データを読み込む（7行目以降）
    df = pd.read_excel(
        filepath, header=None, skiprows=7, names=english_headers, engine="openpyxl"
    )

    # データ読み取りの終端を特定する('#end'が含まれる行を探す)
    end_row = (
        df.index[df.iloc[:, 0] == "#end"].tolist()[0]
        if "#end" in df.iloc[:, 0].values
        else None
    )

    # フォルダ列を除外
    if "folder" in df.columns:
        df = df.drop(columns=["folder"])

    # '#end'より前のデータのみを抽出
    if end_row is not None:
        df = df.iloc[:end_row]

    return df
