# 準備
1. パッケージのインストール  
   注意: このセクションは，ローカル環境でインテリセンスが利くようにするための手順について
   記述している．実際にアプリを動かす際には，venvを作成しなくても良い．

   venvを作成する．
   ```
   .../dsa_back$ python3 -m venv .venv
   ```

   venvをactivateする．
   ```
   .../dsa_back$ . .venv/bin/activate
   ```

   pipでパッケージをインストールする．すると，requirements.txtに書かれたパッケージが.venvに
   インストールされる．
   ```
   .../dsa_back$ pip install -r requirements.txt
   ```

   現在適用しているvenvを解除したい場合は，以下のコマンドを実行する．
   どのディレクトリ上でも実行できる．
   ```
   $ deactivate
   ```

2. 環境変数の設定  
   .env.exampleを参考に，.envファイルを作成する．
   ```bash
   cp .env.example .env
   ```
   opensslをインストールする．
   ```bash
   brew install openssl
   ```
   SECRET_KEYを作成する．
   ```bash
   openssl rand -hex 32
   ```
   最後に.envに作成したSECRET_KEYを貼り付ける．
   ```bash
   # viを使用した例
   vi .env
   # iを押すと入力モードになり編集が可能．(INSERT)
   # 該当箇所にカーソルを移動し，貼り付け
   # escでコマンドモードに戻り，:wqで保存して終了．
   ```
   