# ベースイメージ
FROM python:3.11

# Install Docker-Cli
# Ref: https://docs.docker.com/engine/install/debian/#install-using-the-repository
RUN apt-get update && apt-get install -y ca-certificates curl \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian \
    $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
    tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update && apt-get install -y docker-ce-cli

# dockerizeのバージョンを環境変数として設定
ENV DOCKERIZE_VERSION v0.7.0

# 作業ディレクトリを設定
WORKDIR /app

# dockerizeをダウンロードしてインストール
RUN wget https://github.com/jwilder/dockerize/releases/download/$DOCKERIZE_VERSION/dockerize-linux-amd64-$DOCKERIZE_VERSION.tar.gz \
    && tar -C /usr/local/bin -xzvf dockerize-linux-amd64-$DOCKERIZE_VERSION.tar.gz \
    && rm dockerize-linux-amd64-$DOCKERIZE_VERSION.tar.gz

# 依存関係ファイルをコピー
COPY ./requirements.txt ./

# # dsa_test_caseとdsa_test_programをコンテナ内にコピー
# COPY ./dsa_test_case/ ./dsa_test_case/
# COPY ./dsa_test_program/ ./dsa_test_program/

# アプリケーションコードをコピー
COPY . .

# 依存関係のインストール
RUN pip3 install --no-cache-dir -r requirements.txt

# アプリケーションを起動
CMD ["dockerize", "-wait", "tcp://db:3306", "-timeout", "30s", "uvicorn", "app:app", "--host", "0.0.0.0", "--reload"]
