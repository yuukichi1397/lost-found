import sqlite3
import sqlite_vec

from typing import List
import struct
import os

conn = sqlite3.connect('example.db')

conn.enable_load_extension(True)
sqlite_vec.load(conn)
conn.enable_load_extension(False)
# sqlite-vecの拡張を読み込む（ファイル名は環境に合わせて）
# conn.load_extension("./sqlite_vec.so")  # Mac/Linux
# conn.load_extension("vec0.dll")  # Windows

cursor = conn.cursor()

# ユーザーテーブル作成
# id プライマリキー
# name 名前
# password パスワードのハッシュ
# telenum 電話番号
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, 
        password TEXT,
        telenum TEXT
    )
''')

# グループテーブル作成
# id プライマリキー
# name グループ名
# passkey 自動生成されるパスキー
# place 保管場所
cursor.execute('''
    CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        passkey TEXT,
        place TEXT
    )
''')

# ユーザ・グループテーブル作成
# user_id ユーザidの外部キー
# group_id グループidの外部キー
cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_groups (
    user_id INTEGER NOT NULL,
    group_id INTEGER NOT NULL,
    PRIMARY KEY (user_id, group_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE
    )
''')

# 落とし物DB用ベクトルテーブル作成
cursor.execute("CREATE VIRTUAL TABLE vec_lost USING vec0(embedding float[4])")

# 探し物DB用ベクトルテーブル作成
cursor.execute("CREATE VIRTUAL TABLE vec_search USING vec0(embedding float[4])")

# ベクトルDBというライブラリを使う都合上、
# 落とし物DB用ベクトルテーブルと探し物DB用ベクトルテーブルは分けることにしました


# 落とし物テーブル作成
# id プライマリキー
# type 落とし物の種類
# feature 落とし物の特記事項
# capture_place 落とし物があった場所
# manager 管理者のid(外部キー)
# manage_group 管理しているグループのid(外部キー)
# return_flag 受け渡しフラグ(0→返してない、1→返した)
# picture_path 写真のファイルパス
# return_person 受け渡した人のid(外部キー)
# vector 落とし物DB用ベクトルテーブルのid


cursor.execute('''
    CREATE TABLE IF NOT EXISTS lost (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    feature TEXT,
    capture_place TEXT,
    manager INTEGER,
    manage_group INTEGER,
    return_flag INTEGER,
    picture_path TEXT,
    return_person INTEGER,
    vector INTEGER,
    FOREIGN KEY (manager) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (manage_group) REFERENCES groups(id) ON DELETE CASCADE,
    FOREIGN KEY (return_person) REFERENCES users(id)
    )
''')

# 探し物テーブル作成
# id プライマリキー
# type 落とし物の種類
# feature 落とし物の特記事項
# lost_place 落とした場所
# lost_person 落とした人のid(外部キー)
# return_flag 受け渡しフラグ(0→返してない、1→返した)
# picture_path 写真のファイルパス
# vector 落とし物DB用ベクトルテーブルのid
cursor.execute('''
    CREATE TABLE IF NOT EXISTS search (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    feature TEXT,
    lost_place TEXT,
    lost_person INTEGER,
    return_flag INTEGER,
    picture_path TEXT,
    vector INTEGER,
    FOREIGN KEY (lost_person) REFERENCES users(id) ON DELETE CASCADE
    )
''')

# cursor.execute("INSERT INTO clip (name, embedding) VALUES (?, vector(?))",
#                ("apple", "[0.1, 0.2, 0.3]"))
# cursor.execute("INSERT INTO clip (name, embedding) VALUES (?, vector(?))",
#                ("orange", "[0.3, 0.2, 0.1]"))


# conn.commit()

# query = "[0.1, 0.2, 0.3]"

# cursor.execute("""
# SELECT name, cosine_distance(embedding, vector(?)) AS similarity
# FROM items
# ORDER BY similarity ASC
# LIMIT 5
# """, (query,))

# for row in cursor.fetchall():
#     print(row)

conn.close()