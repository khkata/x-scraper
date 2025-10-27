# X Buzz Scraper

X (旧Twitter) から特定のキーワードを含むバズ投稿（例：いいね数100以上）をスクレイピングし、CSVファイルに保存するPythonスクリプトです。
まだXPathにしてないから注意。

## 機能

- 指定したキーワードでXを検索
- いいね数が閾値以上の投稿を自動収集
- 投稿URL、ユーザー情報、本文、メトリクス（いいね、リポスト、閲覧数）、ハッシュタグを取得
- 収集データをCSV形式で保存（Excel対応）
- 重複投稿の自動除外

## 必要要件

### システム要件

- Python 3.7以上
- Google Chrome ブラウザ
- ChromeDriver

### Pythonパッケージ

```bash
selenium>=4.15.2
webdriver-manager>=4.0.1
pandas>=2.2.0
```

## インストール

1. リポジトリをクローンまたはダウンロード

```bash
git clone https://github.com/khkata/x-scraper.git
cd x-scraper
```

2. 必要なパッケージをインストール

```bash
pip install -r requirements.txt
```

3. ChromeDriverのインストール
[ChromeDriver公式サイト](https://googlechromelabs.github.io/chrome-for-testing/)からダウンロードしてください。

## セットアップ

### デバッグモードでChromeを起動

このスクリプトは既存のChromeセッションに接続するため、事前にデバッグモードでChromeを起動する必要があります。

macOSの場合:
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir="/tmp/chrome_dev"
```

Windowsの場合:
```cmd
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\tmp\chrome_dev"
```

Linuxの場合:
```bash
google-chrome --remote-debugging-port=9222 --user-data-dir="/tmp/chrome_dev"
```

**重要**: デバッグモードで起動したChromeでXにログインしておいてください。

## 使い方

### コマンドライン実行

```bash
python main.py --keyword "#SNS運用" --limit 100
```

#### オプション

- `-k, --keyword`: 検索キーワード（必須）
  - 例: `"#SNS運用"`, `"Python プログラミング"`, `"@username"`
- `-l, --limit`: 収集する投稿の最大件数（デフォルト: 100）

### プログラムから実行

```python
from main import scrape_buzzed_posts

# 50件のバズ投稿を収集
scrape_buzzed_posts(keyword="#SNS運用", limit=50)
```

## 出力データ

収集したデータは`data/buzzed_posts.csv`に保存されます。

### CSVカラム

| カラム名 | 説明 |
|---------|------|
| post_url | 投稿のURL |
| username | ユーザー名 (@id) |
| display_name | 表示名 |
| date | 投稿日時 (ISO 8601形式) |
| text | 投稿本文 |
| likes | いいね数 |
| reposts | リポスト数 |
| views | 閲覧数 |
| hashtags | ハッシュタグ（複数ある場合は\|で区切り） |

### 出力例

```csv
post_url,username,display_name,date,text,likes,reposts,views,hashtags
https://x.com/user/status/123...,@user,ユーザー名,2025-10-27T12:00:00.000Z,投稿本文...,500,100,10000,#SNS運用|#マーケティング
```

## 設定のカスタマイズ

`main.py`内の定数を変更することで、動作をカスタマイズできます：

```python
# いいね数の閾値
LIKE_THRESHOLD = 100

# スクロール間の待機時間（秒）
SCROLL_WAIT_TIME = 1.0

# スクロール量（ピクセル）
SCROLL_STEP = 800

# 最大スクロール回数
MAX_SCROLL_PATIENCE = 5

# 出力ディレクトリ
OUTPUT_DIR = "data"

# 出力ファイル名
OUTPUT_FILENAME = "buzzed_posts.csv"
```

## 注意事項

### HTML構造の変更について

XのHTML構造は頻繁に変更されるため、このスクリプトのセレクタは将来的に機能しなくなる可能性があります。（2025年10月時点での構造に基づいています）

### レート制限

Xにはレート制限があります。大量のデータを収集する場合は、以下の点に注意してください：

- `SCROLL_WAIT_TIME`を長めに設定する
- `limit`を適切な値に設定する
- 連続実行を避ける

### ChromeDriverのパス

スクリプト内のChromeDriverのパスが環境に合わせて設定されています：

```python
service = Service('/opt/homebrew/bin/chromedriver')
```

環境に応じてパスを変更してください。

## トラブルシューティング

### ChromeDriverが見つからない

ChromeDriverのパスを確認し、`setup_driver()`関数内のパスを修正してください。

```bash
which chromedriver
```

### 接続エラー

デバッグモードでChromeが起動していることを確認してください（ポート9222）。

### 投稿が収集できない

- Xにログインしているか確認
- ページの読み込みを待つため、`SCROLL_WAIT_TIME`を増やす
- HTML構造が変更されている可能性があるため、セレクタを確認

## ライセンス

このプロジェクトは個人利用・学習目的で作成されています。

## 免責事項

このツールはWebスクレイピングを行います。利用する際は以下の点に注意してください：

- Xの利用規約を遵守してください
- 過度なリクエストでサーバーに負荷をかけないでください
- 収集したデータの取り扱いには注意してください
- 商用利用の場合は、X APIの利用を検討してください

---

作成日: 2025年10月27日
# x-scraper
