# ベースイメージ
FROM python:3.11

# dockerizeのバージョンを環境変数として設定
ENV DOCKERIZE_VERSION v0.7.0

# 作業ディレクトリを設定
WORKDIR /app

# dockerizeをダウンロードしてインストール
RUN wget https://github.com/jwilder/dockerize/releases/download/$DOCKERIZE_VERSION/dockerize-linux-amd64-$DOCKERIZE_VERSION.tar.gz \
    && tar -C /usr/local/bin -xzvf dockerize-linux-amd64-$DOCKERIZE_VERSION.tar.gz \
    && rm dockerize-linux-amd64-$DOCKERIZE_VERSION.tar.gz

# 依存関係ファイルをコピー
COPY requirements.txt ./

# 依存関係のインストール
RUN pip3 install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY . .

# アプリケーションを起動
CMD ["dockerize", "-wait", "tcp://db:3306", "-timeout", "30s", "uvicorn", "app:app", "--host", "0.0.0.0", "--reload"]
