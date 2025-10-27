#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
X (旧Twitter) から特定のキーワードを含むバズ投稿 (いいね数100以上) を
スクレイピングし、CSVファイルに保存するスクリプト。

XのHTML構造は頻繁に変更されるため、このスクリプトのセレクタは
将来的に機能しなくなる可能性があります。(2025年10月時点での構造に基づく)

実行例:
    # 関数として実行
    from scrape_x import scrape_buzzed_posts
    scrape_buzzed_posts(keyword="#SNS運用", limit=50)

    # コマンドラインから実行
    python scrape_x.py --keyword "#SNS運用" --limit 100
"""

import time
import os
import re
import argparse
from typing import List, Dict, Optional, Any
from urllib.parse import quote

import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException, TimeoutException

# --- 定数定義 ---

# Xの検索URLテンプレート
BASE_URL = "https://x.com/search?q={keyword}&src=typeahead_click"

# スクロール間の待機時間 (秒)
# ページの読み込みが遅い場合や、レート制限を避けるために長めに設定
SCROLL_WAIT_TIME = 1.0

# スクロール量 (ピクセル) - 段階的にスクロールするための値
SCROLL_STEP = 800

# 投稿解析のリトライ回数
MAX_PARSE_RETRIES = 3

# 無限スクロールの最大試行回数 (スクロールしても高さが変わらない場合の許容回数)
MAX_SCROLL_PATIENCE = 5

# いいね数の閾値
LIKE_THRESHOLD = 100

# 出力ディレクトリ
OUTPUT_DIR = "data"
# 出力ファイル名
OUTPUT_FILENAME = "buzzed_posts.csv"

# 取得データのカラム定義
CSV_COLUMNS = [
    'post_url', 'username', 'display_name', 'date', 'text',
    'likes', 'reposts', 'views', 'hashtags'
]


def setup_driver() -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    service = Service('/opt/homebrew/bin/chromedriver')
    driver = webdriver.Chrome(service=service, options=options)
    driver.maximize_window()
    return driver

def convert_to_int(text: str) -> int:
    """
    Xの表示メトリクス (例: "1.5万", "1,234", "10K") を整数に変換します。

    Args:
        text (str): 投稿から取得した生のテキスト。

    Returns:
        int: 変換後の整数値。変換失敗時は0。
    """
    if not text:
        return 0
    
    text = text.strip().replace(',', '')
    
    try:
        if '万' in text:
            num = float(text.replace('万', ''))
            return int(num * 10000)
        if 'K' in text.upper():
            num = float(text.upper().replace('K', ''))
            return int(num * 1000)
        if 'M' in text.upper():
            num = float(text.upper().replace('M', ''))
            return int(num * 1000000)
        
        return int(re.sub(r'\D', '', text))
    except ValueError:
        return 0

def parse_post(article: WebElement) -> Optional[Dict[str, Any]]:
    """
    単一の投稿 (article要素) を解析し、必要なデータを抽出します。
    要素が見つからない場合はリトライ処理を行います。

    Args:
        article (WebElement): 解析対象の投稿のarticle要素。

    Returns:
        Optional[Dict[str, Any]]: 抽出したデータ。失敗した場合はNone。
    """
    
    # リトライ処理
    for attempt in range(MAX_PARSE_RETRIES):
        try:
            # 1. 投稿URLと日時の取得 (timeタグから辿るのが最も確実)
            time_element = article.find_element(By.TAG_NAME, 'time')
            post_date = time_element.get_attribute('datetime')
            
            # time要素の親を辿って <a> タグを見つける
            # これがその投稿のパーマリンク
            ancestor_a = time_element.find_element(By.XPATH, "./ancestor::a[@href]")
            post_url = ancestor_a.get_attribute('href')
            
            # URLが /status/ を含まない場合は広告や関連投稿の可能性があるためスキップ
            if '/status/' not in post_url:
                return None

            # 2. ユーザー情報
            user_name_div = article.find_element(By.CSS_SELECTOR, "div[data-testid='User-Name']")
            # 表示名を取得 (最初のリンク内のspan要素)
            try:
                display_name_element = user_name_div.find_element(By.CSS_SELECTOR, "a[role='link'] span")
                display_name = display_name_element.text
            except NoSuchElementException:
                display_name = ""
            
            # ユーザー名 (@id) - "div[data-testid='User-Name']"の子要素から取得
            try:
                username_elements = user_name_div.find_elements(By.CSS_SELECTOR, "a[role='link']")
                # 2つ目のリンクまたは @を含むテキストを探す
                username = ""
                for elem in username_elements:
                    text = elem.text
                    if text.startswith('@'):
                        username = text
                        break
                if not username and len(username_elements) > 1:
                    username = username_elements[1].text
            except (NoSuchElementException, IndexError):
                username = ""

            # 3. 投稿本文
            try:
                text_div = article.find_element(By.CSS_SELECTOR, "div[data-testid='tweetText']")
                post_text = text_div.text
            except NoSuchElementException:
                # 引用リツイートなどで本文がない場合
                post_text = ""

            # 4. ハッシュタグ
            hashtag_elements = article.find_elements(By.CSS_SELECTOR, "a[href*='/hashtag/']")
            hashtags = "|".join([tag.text for tag in hashtag_elements if tag.text.startswith('#')])

            # 5. メトリクス (いいね、リポスト、閲覧数)
            
            # いいね
            try:
                like_button = article.find_element(By.CSS_SELECTOR, "button[data-testid='like']")
                # ボタン内のすべてのspanを取得し、数値を含むものを探す
                like_spans = like_button.find_elements(By.CSS_SELECTOR, "span")
                like_text = ""
                for span in like_spans:
                    text = span.text.strip()
                    if text and (text.isdigit() or 'K' in text or 'M' in text or '万' in text or ',' in text):
                        like_text = text
                        break
                likes = convert_to_int(like_text)
            except NoSuchElementException:
                likes = 0
            
            # リポスト
            try:
                repost_button = article.find_element(By.CSS_SELECTOR, "button[data-testid='retweet']")
                repost_spans = repost_button.find_elements(By.CSS_SELECTOR, "span")
                repost_text = ""
                for span in repost_spans:
                    text = span.text.strip()
                    if text and (text.isdigit() or 'K' in text or 'M' in text or '万' in text or ',' in text):
                        repost_text = text
                        break
                reposts = convert_to_int(repost_text)
            except NoSuchElementException:
                reposts = 0

            # 閲覧数 (インプレッション)
            # 閲覧数は `a[href$='/analytics']` が最も安定している
            try:
                # "..."/analytics の形式
                analytics_link = article.find_element(By.CSS_SELECTOR, "a[href$='/analytics']")
                views_spans = analytics_link.find_elements(By.CSS_SELECTOR, "span")
                views_text = ""
                for span in views_spans:
                    text = span.text.strip()
                    if text and (text.isdigit() or 'K' in text or 'M' in text or '万' in text or ',' in text):
                        views_text = text
                        break
                views = convert_to_int(views_text)
            except NoSuchElementException:
                # 閲覧数が表示されていない (古い投稿など)
                views = 0

            # すべての解析が成功
            return {
                'post_url': post_url,
                'username': username,
                'display_name': display_name,
                'date': post_date,
                'text': post_text,
                'likes': likes,
                'reposts': reposts,
                'views': views,
                'hashtags': hashtags
            }

        except (NoSuchElementException, StaleElementReferenceException) as e:
            # 要素が見つからない、または要素が古い (DOMが更新された) 場合
            if attempt < MAX_PARSE_RETRIES - 1:
                # リトライ前に少し待機
                time.sleep(0.5)
                continue
            else:
                # print(f"警告: 投稿の解析に失敗しました (リトライ上限)。 {e}")
                return None
        except Exception as e:
            # 予期せぬエラー
            print(f"警告: 予期せぬエラーで投稿の解析に失敗しました。 {e}")
            return None

    return None

def save_data(data: List[Dict[str, Any]], output_path: str, output_format: str = 'csv'):
    """
    収集したデータを指定された形式でファイルに保存します。

    Args:
        data (List[Dict[str, Any]]): 収集した投稿データのリスト。
        output_path (str): 出力ファイルのパス (ディレクトリ含む)。
        output_format (str, optional): 出力形式 ('csv' または 'json')。
    """
    if not data:
        print("保存するデータがありません。")
        return
        
    df = pd.DataFrame(data)
    
    # カラムの順序を定義に従って整える
    # 不足しているカラムがあればNaNで埋める
    df = df.reindex(columns=CSV_COLUMNS)

    # 出力ディレクトリを作成
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    try:
        if output_format == 'csv':
            # Excelでの文字化け防止のため utf-8-sig を使用
            df.to_csv(output_path, index=False, encoding='utf-8-sig')
            print(f"データを {output_path} にCSVとして保存しました。")
        
        elif output_format == 'json':
            # 将来的な拡張用
            json_path = output_path.replace('.csv', '.json')
            df.to_json(json_path, orient='records', force_ascii=False, indent=4)
            print(f"データを {json_path} にJSONとして保存しました。")
            
        else:
            print(f"エラー: サポートされていない出力形式です: {output_format}")

    except Exception as e:
        print(f"エラー: データの保存に失敗しました。 {e}")

def scrape_buzzed_posts(keyword: str, limit: int = 100):
    """
    指定されたキーワードでXを検索し、いいね数が閾値以上の投稿を収集します。

    Args:
        keyword (str): 検索キーワード (例: "#SNS運用")
        limit (int, optional): 収集する投稿の最大件数。
    """
    
    if not keyword:
        print("エラー: キーワードが指定されていません。")
        return

    # URLエンコード
    encoded_keyword = quote(keyword)
    search_url = BASE_URL.format(keyword=encoded_keyword)

    driver = None
    try:
        driver = setup_driver()
        print(f"ページを開いています: {search_url}")
        driver.get(search_url)
        time.sleep(3) # ページ初期ロード待機

        collected_data: List[Dict[str, Any]] = []
        scraped_urls = set() # 重複収集防止用
        
        last_height = driver.execute_script("return document.body.scrollHeight")
        patience = 0 # スクロールしても高さが変わらなかった回数

        print(f"スクレイピング開始... (目標: {limit}件, いいね >= {LIKE_THRESHOLD})")

        scroll_count = 0
        max_scrolls = 50  # 最大スクロール回数
        
        while len(collected_data) < limit and scroll_count < max_scrolls:
            scroll_count += 1
            
            # このスクロールでの処理状況を初期化
            new_posts_found_in_this_scroll = False
            processed_in_this_scroll = 0
            
            # ページ上のすべての投稿 (article要素) を取得
            articles = driver.find_elements(By.CSS_SELECTOR, "article[data-testid='tweet']")

            if not articles:
                print(f"[スクロール {scroll_count}] 投稿が見つかりません。")
                time.sleep(SCROLL_WAIT_TIME)
                # スクロールを続ける
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(SCROLL_WAIT_TIME)
                continue

            for article in articles:
                # 投稿を解析
                post_data = parse_post(article)

                if post_data is None:
                    continue

                post_url = post_data['post_url']
                likes = post_data['likes']

                # 重複チェック
                if post_url in scraped_urls:
                    continue
                
                # すべての投稿を記録(重複防止のため)
                scraped_urls.add(post_url)
                processed_in_this_scroll += 1

                # いいね数チェック
                if likes >= LIKE_THRESHOLD:
                    collected_data.append(post_data)
                    new_posts_found_in_this_scroll = True
                    print(f"[スクロール {scroll_count}] 収集済み: {len(collected_data)}/{limit} 件 (いいね: {likes}) - {post_data['username']}")

                    # 収集件数が上限に達したらループを抜ける
                    if len(collected_data) >= limit:
                        break
            
            # 進捗表示
            print(f"[スクロール {scroll_count}] 処理: {processed_in_this_scroll}件, 新規取得: {'あり' if new_posts_found_in_this_scroll else 'なし'}, 合計: {len(collected_data)}/{limit}")
            
            # --- 無限スクロール処理 ---
            
            # 収集上限に達したらループを抜ける
            if len(collected_data) >= limit:
                print(f"目標件数 {limit} 件に達しました。")
                break
            
            # 段階的にスクロール (一気に最下部まで行かず、少しずつスクロール)
            current_position = driver.execute_script("return window.pageYOffset;")
            driver.execute_script(f"window.scrollBy(0, {SCROLL_STEP});")
            
            # スクロール後に少し待機 (コンテンツの読み込みを待つ)
            time.sleep(SCROLL_WAIT_TIME)
            
            # さらに追加で少しスクロール (遅延読み込みのトリガー)
            time.sleep(1.0)

            # スクロール後の高さを取得
            new_height = driver.execute_script("return document.body.scrollHeight")

            if new_height == last_height:
                # スクロールしてもページの高さが変わらない場合
                if not new_posts_found_in_this_scroll:
                    # このスクロールで新しい投稿も見つからなかった場合
                    patience += 1
                    print(f"[警告] スクロールしても新しい投稿が読み込まれません。(試行 {patience}/{MAX_SCROLL_PATIENCE})")
                    if patience >= MAX_SCROLL_PATIENCE:
                        print("ページの終端に達したか、読み込みが停止したため終了します。")
                        break
                else:
                    # 高さは変わらないが新しい投稿は見つかった場合 (DOMの再利用など)
                    patience = 0 # 忍耐カウントリセット
            else:
                # ページが伸びた場合
                last_height = new_height
                patience = 0 # 忍耐カウントリセット

        print(f"\nスクレイピング終了。合計 {len(collected_data)} 件のバズ投稿を収集しました。")

        # データを保存
        output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILENAME)
        save_data(collected_data, output_path, output_format='csv')

    except Exception as e:
        print(f"エラー: スクレイピングプロセス全体で致命的なエラーが発生しました。 {e}")
    finally:
        if driver:
            driver.quit()
            print("WebDriverを終了しました。")


def main():
    """
    コマンドライン引数を解析し、スクレイピングを実行します。
    """
    parser = argparse.ArgumentParser(
        description=f"X (旧Twitter) からいいね数 {LIKE_THRESHOLD} 以上のバズ投稿をスクレイピングします。",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    parser.add_argument(
        "-k", "--keyword",
        type=str,
        required=True,
        help="検索キーワード (例: \"#SNS運用\")"
    )
    
    parser.add_argument(
        "-l", "--limit",
        type=int,
        default=100,
        help=f"収集する投稿の最大件数 (デフォルト: 100)"
    )

    args = parser.parse_args()

    # 実行例の表示
    print("--- X Buzz Scraper ---")
    print(f"キーワード: {args.keyword}")
    print(f"収集上限: {args.limit} 件")
    print("------------------------")

    scrape_buzzed_posts(
        keyword=args.keyword,
        limit=args.limit,
    )

if __name__ == "__main__":
    main()
