# ベースイメージ
FROM python:3.11

# 作業ディレクトリを設定
WORKDIR /app

# 依存関係ファイルをコピー
COPY requirements.txt ./

# 依存関係のインストール
RUN pip3 install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY . .

# アプリケーションを起動
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--reload"]
