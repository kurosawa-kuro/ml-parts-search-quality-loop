.PHONY: setup build run dev test fmt lint clean

# Application
APP_NAME := <your-project>

# 初期セットアップ (依存取得・ビルド)
setup: deps build
	@echo "Setup complete."

deps:
	@echo "TODO: 依存をインストール (例: npm install / cargo fetch / pip install -r requirements.txt)"

# ビルド
build:
	@echo "TODO: ビルドコマンドを記述"

# 実行
run:
	@echo "TODO: 実行コマンドを記述"

# 開発 (ホットリロード)
dev:
	@echo "TODO: 開発サーバー / watch コマンドを記述"

# テスト
test:
	@echo "TODO: テストコマンドを記述"

# 整形
fmt:
	@echo "TODO: フォーマッタを記述"

# 静的解析
lint:
	@echo "TODO: リンタを記述"

# クリーンアップ
clean:
	@echo "TODO: 成果物削除コマンドを記述"
