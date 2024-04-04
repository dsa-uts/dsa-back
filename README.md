# 準備
1. パッケージのインストール  
   以下のコマンドで，必要なパッケージ(requirements.txtに書かれたもの)が一括でインストールされる．
   ```bash
   pip3 install -r requirements.txt
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
   