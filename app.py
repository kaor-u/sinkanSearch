import os
import sqlite3
import requests
import smtplib
import re

from datetime import datetime, timedelta

from email.mime.text import MIMEText
from email.utils import formatdate

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for
)

from pykakasi import kakasi


# =========================================================
# Flask
# =========================================================

app = Flask(__name__)


# =========================================================
# データベース
# =========================================================

DB_PATH = os.path.join(
    os.path.dirname(
        os.path.abspath(__file__)
    ),
    "books.db"
)


# =========================================================
# 楽天ブックスAPI設定
# =========================================================

RAKUTEN_BOOKS_API_URL = (
    "https://openapi.rakuten.co.jp/"
    "services/api/BooksBook/Search/20170404"
)


# ここには自分の値を入れてください
# チャットにはキーそのものを貼らないでください。

RAKUTEN_APPLICATION_ID = ""

RAKUTEN_ACCESS_KEY = ""

# =========================================================
# Gmail設定
# =========================================================

MY_EMAIL = ""

APP_PASSWORD = ""


# =========================================================
# シリーズ名を並べ替えるための関数
# =========================================================

def get_reading(text):
    """
    日本語の文字列をひらがなに変換する。

    例：
        葬送のフリーレン
        ↓
        そうそうのふりーれん
    """

    if not text:
        return ""

    text = str(text).strip()

    if not text:
        return ""

    converter = kakasi()

    result = converter.convert(text)

    reading = "".join(
        item["hira"]
        for item in result
    )

    return reading


def series_sort_key(series_name):
    """
    シリーズ名を五十音順・アルファベット順に
    並べるためのソートキー。

    英字・数字で始まるもの
        → アルファベット・数字順

    日本語で始まるもの
        → 読み仮名による五十音順

    空欄
        → 最後
    """

    if not series_name:
        return (
            2,
            ""
        )

    text = str(
        series_name
    ).strip()

    if not text:
        return (
            2,
            ""
        )

    first = text[0]

    # -----------------------------------------------------
    # 英字・数字
    # -----------------------------------------------------

    if first.isascii() and first.isalnum():

        return (
            0,
            text.lower()
        )

    # -----------------------------------------------------
    # 日本語
    # -----------------------------------------------------

    reading = get_reading(
        text
    )

    return (
        1,
        reading,
        text
    )


# =========================================================
# タイトルの並び替え用
# =========================================================

def title_sort_key(title):
    """
    タイトルも日本語なら読みを使って並べる。
    """

    if not title:
        return (
            "",
            ""
        )

    text = str(
        title
    ).strip()

    reading = get_reading(
        text
    )

    return (
        reading,
        text
    )


def extract_volume(title):
    """
    タイトルの末尾や途中にある（1）や (12) などの巻数を抽出する。
    対応：(1), （12）, [3], 【4】などの全角半角の数字
    """
    if not title:
        return None

    # タイトルから括弧で囲まれた数字（全角・半角）を探すパターン
    # 例: 「葬送のフリーレン（12）」から 12 を見つける
    match = re.search(r'[（\(\[【]([0-9０-９]+)[）\)\]】]', title)
    if match:
        # 見つかった数字を半角の整数(int)に変換して返す
        vol_str = match.group(1)
        # 全角数字を半角に変換する簡易処理
        vol_str = vol_str.translate(str.maketrans('０１２３４５６７８９', '0123456789'))
        return int(vol_str)

    return None

# =========================================================
# Gmailを送る
# =========================================================

def send_gmail(
    subject,
    body
):

    msg = MIMEText(
        body,
        "plain",
        "utf-8"
    )

    msg["Subject"] = subject

    msg["From"] = MY_EMAIL

    msg["To"] = MY_EMAIL

    msg["Date"] = formatdate(
        localtime=True
    )

    try:

        server = smtplib.SMTP_SSL(
            "smtp.gmail.com",
            465,
            timeout=10
        )

        server.login(
            MY_EMAIL,
            APP_PASSWORD
        )

        server.send_message(
            msg
        )

        server.quit()

        print(
            "✅ メール送信成功"
        )

        return True

    except Exception as e:

        print(
            f"❌ メール送信失敗: {e}"
        )

        return False


# =========================================================
# ISBNを整える
# =========================================================

def normalize_isbn(isbn):

    if not isbn:
        return ""

    isbn = str(
        isbn
    )

    isbn = isbn.replace(
        "-",
        ""
    )

    isbn = isbn.replace(
        " ",
        ""
    )

    isbn = isbn.replace(
        "　",
        ""
    )

    return isbn.strip()


# =========================================================
# データベース初期化
# =========================================================

def init_db():
    print()
    print("===== データベース確認 =====")
    print(f"読み込むDB: {DB_PATH}")
    print(f"DBファイル存在: {os.path.exists(DB_PATH)}")
    print("============================")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # -----------------------------------------------------
    # booksテーブルを作成
    # -----------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT,
            series_name TEXT,
            book_type TEXT DEFAULT '',
            genre TEXT DEFAULT '',
            status TEXT,
            comment TEXT DEFAULT '',
            cover_url TEXT DEFAULT '',
            volume INTEGER DEFAULT NULL
        )
    """)

    # -----------------------------------------------------
    # 現在存在する列を確認
    # -----------------------------------------------------

    cursor.execute("""
        PRAGMA table_info(books)
    """)

    columns = {
        row[1]
        for row in cursor.fetchall()
    }

    # -----------------------------------------------------
    # 不足している列だけ追加
    # -----------------------------------------------------

    if "comment" not in columns:

        cursor.execute("""
            ALTER TABLE books
            ADD COLUMN comment TEXT DEFAULT ''
        """)

    if "cover_url" not in columns:

        cursor.execute("""
            ALTER TABLE books
            ADD COLUMN cover_url TEXT DEFAULT ''
        """)

    if "book_type" not in columns:

        cursor.execute("""
            ALTER TABLE books
            ADD COLUMN book_type TEXT DEFAULT ''
        """)

    if "genre" not in columns:

        cursor.execute("""
            ALTER TABLE books
            ADD COLUMN genre TEXT DEFAULT ''
        """)

    if "volume" not in columns:

        cursor.execute("""
            ALTER TABLE books
            ADD COLUMN volume INTEGER DEFAULT NULL
        """)

    # -----------------------------------------------------
    # 保存
    # -----------------------------------------------------

    conn.commit()

    # -----------------------------------------------------
    # DBを閉じる
    # -----------------------------------------------------

    conn.close()

    print("データベースの初期化が完了しました。")



# =========================================================
# 本を取得
# =========================================================

def get_books(
    series_name="",
    book_type="",
    genre="",
    sort_order="registered"
):

    conn = sqlite3.connect(
        DB_PATH
    )

    conn.row_factory = sqlite3.Row

    query = """
        SELECT
            id,
            title,
            author,
            series_name,
            book_type,
            genre,
            status,
            comment,
            cover_url,
            volume
        FROM books
        WHERE 1 = 1
    """

    params = []

    # -----------------------------------------------------
    # シリーズ絞り込み
    # -----------------------------------------------------

    if series_name:

        query += """
            AND series_name = ?
        """

        params.append(
            series_name
        )

    # -----------------------------------------------------
    # 形態絞り込み
    # -----------------------------------------------------

    if book_type:

        query += """
            AND book_type = ?
        """

        params.append(
            book_type
        )

    # -----------------------------------------------------
    # ジャンル絞り込み
    # -----------------------------------------------------

    if genre:

        query += """
            AND genre = ?
        """

        params.append(
            genre
        )

    # -----------------------------------------------------
    # SQLで並べる場合
    # -----------------------------------------------------

    if sort_order == "title":

        query += """
            ORDER BY
                title COLLATE NOCASE ASC
        """

    elif sort_order == "type":

        query += """
            ORDER BY
                book_type COLLATE NOCASE ASC,
                title COLLATE NOCASE ASC
        """

    elif sort_order == "genre":

        query += """
            ORDER BY
                genre COLLATE NOCASE ASC,
                title COLLATE NOCASE ASC
        """


    elif sort_order == "volume":

        query += """

            ORDER BY

                CASE

                    WHEN series_name IS NULL

                         OR TRIM(series_name) = ''

                    THEN 1

                    ELSE 0

                END,

                series_name COLLATE NOCASE ASC,

                CASE

                    WHEN volume IS NULL THEN 1

                    ELSE 0

                END,

                volume ASC,

                title COLLATE NOCASE ASC

        """



    elif sort_order == "series":

        query += """

            ORDER BY

                series_name COLLATE NOCASE ASC,

                volume ASC,

                title COLLATE NOCASE ASC

        """

        # -------------------------------------------------
        # シリーズ順は後でPython側で処理する
        # -------------------------------------------------

        query += """
            ORDER BY id ASC
        """

    else:

        query += """
            ORDER BY id ASC
        """

    books = conn.execute(
        query,
        params
    ).fetchall()

    conn.close()

    # =====================================================
    # シリーズ順
    # =====================================================

    if sort_order == "series":

        books = sorted(
            books,
            key=lambda book: (
                series_sort_key(
                    book["series_name"]
                ),
                title_sort_key(
                    book["title"]
                )
            )
        )

    return books


# =========================================================
# 本棚に登録されているシリーズ名を取得
# =========================================================

def get_series_names():

    conn = sqlite3.connect(
        DB_PATH
    )

    rows = conn.execute("""
        SELECT DISTINCT series_name
        FROM books
        WHERE series_name IS NOT NULL
        AND TRIM(series_name) != ''
        ORDER BY series_name
    """).fetchall()

    conn.close()

    series_names = [
        row[0].strip()
        for row in rows
        if row[0]
    ]

    return series_names


# =========================================================
# 本棚に登録されている形態を取得
# =========================================================

def get_book_types():

    conn = sqlite3.connect(
        DB_PATH
    )

    rows = conn.execute("""
        SELECT DISTINCT book_type
        FROM books
        WHERE book_type IS NOT NULL
        AND TRIM(book_type) != ''
        ORDER BY book_type
    """).fetchall()

    conn.close()

    book_types = [
        row[0].strip()
        for row in rows
        if row[0]
    ]

    return book_types


# =========================================================
# 本棚に登録されているジャンルを取得
# =========================================================

def get_genres():

    conn = sqlite3.connect(
        DB_PATH
    )

    rows = conn.execute("""
        SELECT DISTINCT genre
        FROM books
        WHERE genre IS NOT NULL
        AND TRIM(genre) != ''
        ORDER BY genre
    """).fetchall()

    conn.close()

    genres = [
        row[0].strip()
        for row in rows
        if row[0]
    ]

    return genres


# =========================================================
# 1冊取得
# =========================================================

def get_book(book_id):

    conn = sqlite3.connect(
        DB_PATH
    )

    conn.row_factory = sqlite3.Row

    book = conn.execute("""
        SELECT
            id,
            title,
            author,
            series_name,
            book_type,
            genre,
            status,
            comment,
            cover_url,
            volume
        FROM books
        WHERE id = ?
    """, (
        book_id,
    )).fetchone()

    conn.close()

    return book


# =========================================================
# 本を追加
# =========================================================

def add_book(
    title,
    author="",
    series_name="",
    book_type="",
    genre="",
    status="読みたい本",
    comment="",
    cover_url="",
    volume=None
):


    conn = sqlite3.connect(
        DB_PATH
    )

    conn.execute("""
        INSERT INTO books (
            title,
            author,
            series_name,
            book_type,
            genre,
            status,
            comment,
            cover_url,
            volume
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        title,
        author,
        series_name,
        book_type,
        genre,
        status,
        comment,
        cover_url,
        volume
    ))

    conn.commit()

    conn.close()


# =========================================================
# 本を削除
# =========================================================

def delete_book(book_id):

    conn = sqlite3.connect(
        DB_PATH
    )

    conn.execute(
        "DELETE FROM books WHERE id = ?",
        (book_id,)
    )

    conn.commit()

    conn.close()


# =========================================================
# 本を更新
# =========================================================

def update_book(
    book_id,
    title,
    author,
    series_name,
    book_type,
    genre,
    status,
    comment,
    cover_url,
    volume
):

    conn = sqlite3.connect(
        DB_PATH
    )

    conn.execute("""
        UPDATE books
        SET
            title = ?,
            author = ?,
            series_name = ?,
            book_type = ?,
            genre = ?,
            status = ?,
            comment = ?,
            cover_url = ?,
            volume = ?
        WHERE id = ?
    """, (
        title,
        author,
        series_name,
        book_type,
        genre,
        status,
        comment,
        cover_url,
        volume,
        book_id
    ))

    conn.commit()

    conn.close()



# =========================================================
# 楽天ブックスAPI検索
# =========================================================

def search_rakuten_books(
    keyword="",
    isbn="",
    author=""
):

    # -----------------------------------------------------
    # APIキー確認
    # -----------------------------------------------------

    if not RAKUTEN_APPLICATION_ID:

        print(
            "楽天Application IDが設定されていません。"
        )

        return []

    if not RAKUTEN_ACCESS_KEY:

        print(
            "楽天Access Keyが設定されていません。"
        )

        return []

    # -----------------------------------------------------
    # 検索条件
    # -----------------------------------------------------

    params = {

        "applicationId":
            RAKUTEN_APPLICATION_ID,

        "accessKey":
            RAKUTEN_ACCESS_KEY,

        "format":
            "json",

        "hits":
            20,

        "page":
            1

    }

    # -----------------------------------------------------
    # ISBN検索
    # -----------------------------------------------------

    if isbn:

        isbn = normalize_isbn(
            isbn
        )

        params["isbn"] = isbn

    # -----------------------------------------------------
    # 著者検索
    # -----------------------------------------------------

    elif author:

        params["author"] = author

    # -----------------------------------------------------
    # タイトルなどのキーワード検索
    # -----------------------------------------------------

    elif keyword:

        params["title"] = keyword

    else:

        return []

    # -----------------------------------------------------
    # APIアクセス
    # -----------------------------------------------------

    try:

        response = requests.get(
            RAKUTEN_BOOKS_API_URL,
            params=params,
            timeout=10
        )

        print()
        print(
            "===== 楽天ブックスAPI ====="
        )

        print(
            f"ステータス: "
            f"{response.status_code}"
        )

        print(
            f"URL: "
            f"{response.url}"
        )

        response.raise_for_status()

        data = response.json()

    except Exception as e:

        print(
            f"楽天ブックスAPIエラー: {e}"
        )

        return []

    # -----------------------------------------------------
    # 検索結果
    # -----------------------------------------------------

    results = []

    for item in data.get(
        "Items",
        []
    ):

        book = item.get(
            "Item",
            item
        )

        title = book.get(
            "title",
            ""
        )

        author = book.get(
            "author",
            ""
        )

        publisher = book.get(
            "publisherName",
            ""
        )

        isbn_result = normalize_isbn(
            book.get(
                "isbn",
                ""
            )
        )

        sales_date = book.get(
            "salesDate",
            ""
        )

        item_price = book.get(
            "itemPrice",
            ""
        )

        item_url = book.get(
            "itemUrl",
            ""
        )

        small_image_url = book.get(
            "smallImageUrl",
            ""
        )

        medium_image_url = book.get(
            "mediumImageUrl",
            ""
        )

        review_count = book.get(
            "reviewCount",
            0
        )

        review_average = book.get(
            "reviewAverage",
            0
        )

        results.append({

            "title":
                title,

            "author":
                author,

            "publisher":
                publisher,

            "isbn":
                isbn_result,

            "sales_date":
                sales_date,

            "price":
                item_price,

            "item_url":
                item_url,

            "cover_url": (
                medium_image_url
                or small_image_url
            ),

            "review_count":
                review_count,

            "review_average":
                review_average

        })

    print(
        f"検索結果: {len(results)}件"
    )

    print(
        "============================"
    )

    return results


# =========================================================
# 本棚
# =========================================================

@app.route("/")
def index():

    # -----------------------------------------------------
    # 絞り込み条件
    # -----------------------------------------------------

    selected_series = request.args.get(
        "series",
        ""
    ).strip()

    selected_type = request.args.get(
        "book_type",
        ""
    ).strip()

    selected_genre = request.args.get(
        "genre",
        ""
    ).strip()

    sort_order = request.args.get(
        "sort",
        "registered"
    ).strip()

    # -----------------------------------------------------
    # 本を取得
    # -----------------------------------------------------

    books = get_books(
        series_name=selected_series,
        book_type=selected_type,
        genre=selected_genre,
        sort_order=sort_order
    )

    # -----------------------------------------------------
    # 選択肢を取得
    # -----------------------------------------------------

    series_names = get_series_names()

    book_types = get_book_types()

    genres = get_genres()

    return render_template(
        "index.html",
        books=books,
        search_results=[],
        search_keyword="",
        search_isbn="",
        search_author="",

        series_names=series_names,
        book_types=book_types,
        genres=genres,

        selected_series=selected_series,
        selected_type=selected_type,
        selected_genre=selected_genre,
        sort_order=sort_order
    )


# =========================================================
# 楽天ブックス検索
# =========================================================

@app.route(
    "/search",
    methods=["GET", "POST"]
)
def search():

    if request.method == "POST":

        keyword = request.form.get(
            "keyword",
            ""
        ).strip()

        isbn = request.form.get(
            "isbn",
            ""
        ).strip()

        author = request.form.get(
            "author",
            ""
        ).strip()

    else:

        keyword = request.args.get(
            "keyword",
            ""
        ).strip()

        isbn = request.args.get(
            "isbn",
            ""
        ).strip()

        author = request.args.get(
            "author",
            ""
        ).strip()

    # -----------------------------------------------------
    # 楽天API検索
    # -----------------------------------------------------

    search_results = search_rakuten_books(
        keyword=keyword,
        isbn=isbn,
        author=author
    )

    books = get_books()

    return render_template(
        "index.html",
        books=books,
        search_results=search_results,
        search_keyword=keyword,
        search_isbn=isbn,
        search_author=author,

        series_names=get_series_names(),
        book_types=get_book_types(),
        genres=get_genres(),

        selected_series="",
        selected_type="",
        selected_genre="",
        sort_order="registered"
    )


# =========================================================
# 楽天検索結果から本棚へ追加
# =========================================================

@app.route(
    "/add",
    methods=["POST"]
)
def add():

    title = request.form.get(
        "title",
        ""
    ).strip()

    author = request.form.get(
        "author",
        ""
    ).strip()

    series_name = request.form.get(
        "series_name",
        ""
    ).strip()

    book_type = request.form.get(
        "book_type",
        ""
    ).strip()

    genre = request.form.get(
        "genre",
        ""
    ).strip()

    status = request.form.get(
        "status",
        "読みたい本"
    ).strip()

    comment = request.form.get(
        "comment",
        ""
    ).strip()

    cover_url = request.form.get(
        "cover_url",
        ""
    ).strip()

    # -----------------------------------------------------
    # タイトルから巻数を自動取得
    # -----------------------------------------------------

    volume = extract_volume(
        title
    )


    # タイトルから巻数を自動取得
    volume = extract_volume(title)

    if title:
        add_book(
            title=title,
            author=author,
            series_name=series_name,
            book_type=book_type,
            genre=genre,
            status=status,
            comment=comment,
            cover_url=cover_url,
            volume=volume
        )

    return redirect(
        url_for("index")
    )


# =========================================================
# 本の詳細
# =========================================================

@app.route(
    "/book/<int:book_id>"
)
def book_detail(book_id):

    book = get_book(
        book_id
    )

    if book is None:

        return (
            "本が見つかりません",
            404
        )

    return render_template(
        "book_detail.html",
        book=book
    )


# =========================================================
# 本の訂正
# =========================================================

@app.route(
    "/book/<int:book_id>/edit",
    methods=["POST"]
)
def edit_book(book_id):

    title = request.form.get(
        "title",
        ""
    ).strip()

    author = request.form.get(
        "author",
        ""
    ).strip()

    series_name = request.form.get(
        "series_name",
        ""
    ).strip()

    book_type = request.form.get(
        "book_type",
        ""
    ).strip()

    genre = request.form.get(
        "genre",
        ""
    ).strip()

    status = request.form.get(
        "status",
        ""
    ).strip()

    comment = request.form.get(
        "comment",
        ""
    ).strip()

    cover_url = request.form.get(
        "cover_url",
        ""
    ).strip()

    volume_text = request.form.get(
        "volume",
        ""
    ).strip()

    try:
        volume = int(volume_text) if volume_text else None
    except ValueError:
        volume = None


    if title:

        update_book(
            book_id,
            title,
            author,
            series_name,
            book_type,
            genre,
            status,
            comment,
            cover_url,
            volume
        )

    return redirect(
        url_for(
            "book_detail",
            book_id=book_id
        )
    )


# =========================================================
# 新刊チェック
# =========================================================

@app.route(
    "/check-new-books",
    methods=["POST"]
)
def check_new_books_route():

    success, message = check_new_books()

    return render_template(
        "index.html",
        books=get_books(),
        search_results=[],
        search_keyword="",
        search_isbn="",
        search_author="",

        series_names=get_series_names(),
        book_types=get_book_types(),
        genres=get_genres(),

        selected_series="",
        selected_type="",
        selected_genre="",
        sort_order="registered",

        message=message,
        message_success=success
    )


# =========================================================
# 本の削除
# =========================================================

@app.route(
    "/book/<int:book_id>/delete",
    methods=["POST"]
)
def remove_book(book_id):

    delete_book(
        book_id
    )

    return redirect(
        url_for("index")
    )


# =========================================================
# 新刊チェック
# =========================================================

def check_new_books():

    books = get_books()

    # -----------------------------------------------------
    # 本棚に登録されているシリーズ名
    # -----------------------------------------------------

    series_names = []

    for book in books:

        series_name = (
            book["series_name"]
            or ""
        ).strip()

        if not series_name:
            continue

        if series_name not in series_names:

            series_names.append(
                series_name
            )

    # -----------------------------------------------------
    # シリーズがない場合
    # -----------------------------------------------------

    if not series_names:

        return (
            False,
            "本棚にシリーズ名が登録されている本がありません。"
        )

    # -----------------------------------------------------
    # 本棚にすでに登録されているタイトル
    # -----------------------------------------------------

    registered_titles = set()

    for book in books:

        title = (
            book["title"]
            or ""
        ).strip()

        if title:

            registered_titles.add(
                title
            )

    # -----------------------------------------------------
    # 今日の日付
    # -----------------------------------------------------

    today = datetime.now().date()

    limit_date = today + timedelta(
        days=60
    )

    # -----------------------------------------------------
    # メール本文
    # -----------------------------------------------------

    body_lines = [

        "📚 本棚の新刊チェック結果",

        "",

        f"チェック日："
        f"{today.strftime('%Y/%m/%d')}",

        f"対象期間："
        f"{today.strftime('%Y/%m/%d')} ～ "
        f"{limit_date.strftime('%Y/%m/%d')}",

        ""

    ]

    found_books = []

    # -----------------------------------------------------
    # シリーズごとに楽天ブックス検索
    # -----------------------------------------------------

    for series_name in series_names:

        print()
        print(
            "================================"
        )

        print(
            f"📚 シリーズ検索: {series_name}"
        )

        print(
            "================================"
        )

        results = search_rakuten_books(
            keyword=series_name
        )

        # -------------------------------------------------
        # 検索結果を確認
        # -------------------------------------------------

        for book in results:

            title = (
                book["title"]
                or ""
            ).strip()

            if not title:
                continue

            # -------------------------------------------------
            # 本棚にすでにある本は除外
            # -------------------------------------------------

            if title in registered_titles:

                print(
                    f"既に本棚にあります: {title}"
                )

                continue

            # -------------------------------------------------
            # 発売日の確認
            # -------------------------------------------------

            sales_date_text = (
                book["sales_date"]
                or ""
            ).strip()

            if not sales_date_text:

                print(
                    f"発売日不明のため除外: {title}"
                )

                continue

            try:

                sales_date_text = (
                    sales_date_text
                    .replace("年", "-")
                    .replace("月", "-")
                    .replace("日", "")
                )

                sales_date = datetime.strptime(
                    sales_date_text,
                    "%Y-%m-%d"
                ).date()

            except ValueError:

                print(
                    f"発売日を解析できません: "
                    f"{book['sales_date']}"
                )

                continue

            # -------------------------------------------------
            # 2か月先までか確認
            # -------------------------------------------------

            if sales_date < today:

                print(
                    f"発売済みなので除外: {title}"
                )

                continue

            if sales_date > limit_date:

                print(
                    f"2か月より先なので除外: {title}"
                )

                continue

            # -------------------------------------------------
            # 新刊として登録
            # -------------------------------------------------

            found_books.append({

                "series":
                    series_name,

                "title":
                    title,

                "author":
                    book["author"],

                "sales_date":
                    sales_date,

                "isbn":
                    book["isbn"],

                "price":
                    book["price"],

                "item_url":
                    book["item_url"]

            })

    # -----------------------------------------------------
    # 新刊がなかった場合
    # -----------------------------------------------------

    if not found_books:

        body_lines.append(
            "該当する新刊はありませんでした。"
        )

    else:

        body_lines.append(
            f"{len(found_books)}冊の新刊候補が見つかりました。"
        )

        body_lines.append("")

        found_books.sort(
            key=lambda x: x["sales_date"]
        )

        for book in found_books:

            body_lines.append(
                f"【{book['series']}】"
            )

            body_lines.append(
                f"タイトル: {book['title']}"
            )

            body_lines.append(
                f"著者: "
                f"{book['author'] or '不明'}"
            )

            body_lines.append(
                f"発売日: "
                f"{book['sales_date'].strftime('%Y/%m/%d')}"
            )

            body_lines.append(
                f"ISBN: "
                f"{book['isbn'] or '不明'}"
            )

            body_lines.append(
                f"価格: "
                f"{book['price'] or '不明'}円"
            )

            body_lines.append(
                f"楽天URL: "
                f"{book['item_url'] or 'なし'}"
            )

            body_lines.append("")

    # -----------------------------------------------------
    # メール送信
    # -----------------------------------------------------

    body = "\n".join(
        body_lines
    )

    print()
    print(
        "===== 新刊チェック結果 ====="
    )

    print(body)

    print(
        "============================"
    )

    subject = (
        "【本棚】新刊チェック結果"
    )

    success = send_gmail(
        subject,
        body
    )

    # -----------------------------------------------------
    # 結果
    # -----------------------------------------------------

    if success:

        return (
            True,
            f"新刊チェック完了。"
            f"{len(found_books)}冊をメールしました。"
        )

    return (
        False,
        "新刊チェックは完了しましたが、"
        "メール送信に失敗しました。"
    )


# =========================================================
# 起動
# =========================================================

if __name__ == "__main__":

    init_db()

    app.run(
        debug=True
    )
