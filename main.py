from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
import sqlite3
from typing import List, Dict, Any, Optional
import sqlite_vec
import uuid
import os
import asyncio
from io import BytesIO


app = FastAPI()

DB_PATH = "example.db"
FILE = "./example.db"

# 落とし物DBの閲覧用関数
def get_lost_items(user_id: int) -> List[Dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 管理者が所属するグループを取得
    cursor.execute("""
        SELECT group_id FROM user_groups WHERE user_id = ?
    """, (user_id,))
    group_ids = [row["group_id"] for row in cursor.fetchall()]

    if not group_ids:
        conn.close()
        raise HTTPException(status_code=404, detail="ユーザーがグループに所属していません")

    # print(group_ids)

    # 落とし物テーブルから管理しているグループの落とし物を取得
    placeholders = ','.join(['?'] * len(group_ids)) # placeholdersに?,?,?,?⋯というクエリに必要なやつを動的に作る
    query = f"""
        SELECT * FROM lost
        WHERE manage_group IN ({placeholders})
    """
    cursor.execute(query, group_ids)
    rows = cursor.fetchall()
    conn.close()

    # fastapiではdictを勝手にjsonに変換するらしいため、SQLite Row → dict に変換する
    return [dict(row) for row in rows]

# 落とし物DB閲覧用関数の実行をするためのエンドポイント
@app.get("/{user_id}/lost_items")
def read_lost_items(user_id: int):
    return get_lost_items(user_id)

# 落とし物idから落とし物テーブルのレコードを取得
@app.get("/{item_id}/get_lost_item_from_item_id")
def get_lost_item_from_item_id(item_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM lost WHERE id = ?
    """, (item_id,))

    rows = cursor.fetchall()
    conn.close()
    if rows is None:
        raise HTTPException(status_code=404, detail="指定されたIDのレコードが存在しません")

    return [dict(row) for row in rows]

# ユーザidで返却依頼テーブルを検索
@app.get("/{user_id}/get_receipt_request_from_userid")
def get_receipt_request_from_userid(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()
    cursor.execute("""
        SELECT lost_item_id FROM receipt_request WHERE user_id = ?
    """, (user_id,))

    rows = cursor.fetchall()
    conn.close()
    if rows is None:
        raise HTTPException(status_code=404, detail="指定されたIDのレコードが存在しません")

    return [dict(row) for row in rows]

# 落とし物idで返却依頼テーブルを検索
@app.get("/{item_id}/get_receipt_request_from_itemid")
def get_receipt_request_from_itemid(item_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id FROM receipt_request WHERE lost_item_id = ?
    """, (item_id,))

    rows = cursor.fetchall()
    conn.close()
    if rows is None:
        raise HTTPException(status_code=404, detail="指定されたIDのレコードが存在しません")

    return [dict(row) for row in rows]

# 落とし物DBの変更用関数(関数ではないが)
class UpdateLostItem(BaseModel):
    id: int        # 対象のレコードID
    field: str     # 変更するカラム名
    value: Any     # 新しい値（str,int等）

@app.put("/lost/update")
def update_lost_item(data: UpdateLostItem) -> Dict:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # カラム名のチェック(SQLインジェクションへの対策用)
    allowed_fields = {
        "capture_date", "capture_place", "manager",
        "manage_group", "return_flag", "picture_path",
        "return_person", "vector"
    }

    if data.field not in allowed_fields:
        conn.close()
        raise HTTPException(status_code=400, detail=f"無効なカラム名: {data.field}")

    # print(data.field)

    # クエリを構築（valueは?プレースホルダで渡す）
    # 調べてみた感じ、data.fieldの部分は?使えないっぽいからdata.fieldで固定した
    query = f"UPDATE lost SET {data.field} = ? WHERE id = ?"
    cursor.execute(query, (data.value, data.id))
    conn.commit()

    # 更新されたレコードを取得して返す
    cursor.execute("SELECT * FROM lost WHERE id = ?", (data.id,))
    row = cursor.fetchone()
    conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail="指定されたIDのレコードが存在しません")

    # fastapiではdictを勝手にjsonに変換するらしいため、row → dict に変換する
    return dict(row)


# user_idを入力するとusersテーブルのレコードを返すAPI
@app.get("/{user_id}/get_user")
def get_user_data(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    # 管理者が所属するグループを取得
    cursor.execute("""
        SELECT * FROM users WHERE id = ?
    """, (user_id,))

    rows = cursor.fetchall()
    conn.close()
    if rows is None:
        raise HTTPException(status_code=404, detail="指定されたIDのレコードが存在しません")

    return [dict(row) for row in rows]

# group_idを入力するとgroupsテーブルのレコードを返すAPI
@app.get("/{group_id}/get_group")
def get_user_data(group_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM groups WHERE id = ?
    """, (group_id,))

    rows = cursor.fetchall()
    conn.close()
    if rows is None:
        raise HTTPException(status_code=404, detail="指定されたIDのレコードが存在しません")

    return [dict(row) for row in rows]

# 落とし物情報の登録
# in: 画像、種類、特徴、位置情報、管理者、管理グループ
# 処理: ベクトル化、落とし物DBへ登録、画像の保存
# out: 終了ステータス
os.makedirs("./images", exist_ok=True)

# 落とし物クラス
class LostItem(BaseModel):
    capture_date: str              # 拾った日付
    capture_place: str             # 位置情報
    img_path: str                  # 画像のパス
    manager: int                   # 管理者のid
    manage_group: int              # 管理グループのid
    vector: int                    # ベクトルテーブルのid


@app.post("/register_lost_item/")
async def register_lost_item(
    capture_date: str = Form(...),          # 拾った日付
    image: UploadFile = File(...),          # 画像
    capture_place: str = Form(...),         # 位置情報
    manager: int = Form(...),               # 管理者
    manage_group: int = Form(...),          # 管理者グループ
    vector: int = Form(...)                 # ベクトルテーブルのid
):

    # 画像のパスを設定
    ext = os.path.splitext(image.filename)[1]
    image_path = f"./images/{uuid.uuid4().hex}{ext}"

    # 画像の保存
    try:
        with open(image_path, "wb") as f:
            f.write(await image.read())
    except Exception as e:
        return {"ERROR: Failed to save image. ": str(e)}
    
    # LostItem を自分で組み立てる
    lost_item = LostItem(
        capture_date=capture_date,
        capture_place=capture_place,
        img_path=image_path, 
        manager=manager,
        manage_group=manage_group,
        vector=vector,
    )

    # よくわからんからとりあえず変数にした
    return_flag=0
    
    # DB接続
    conn = sqlite3.connect(FILE)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    cursor = conn.cursor()


    try:
        # DBにデータを挿入
        cursor.execute('''
        INSERT INTO lost (capture_date, capture_place, manager, manage_group,
                            return_flag, picture_path, return_person, vector)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (lost_item.capture_date, lost_item.capture_place, manager, manage_group, return_flag, lost_item.img_path, None, lost_item.vector))

        # idを取得
        inserted_id = cursor.lastrowid
        conn.commit()

        return {
            "status": "SUCCESS",
            "message": "Lost item registered successfully",
            "image_path": lost_item.img_path,
            "db_item_id": inserted_id,
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "message": f"failed to register Lost item {str(e)}",
            "image_path": lost_item.img_path,
            "db_item_id": None,
        }
    
    finally:
        conn.close()


# 探し物物情報の登録
# in: 種類、特徴、
# 処理: 探し物DBへ登録、画像の保存
# out: 終了ステータス
# 探し物クラス
class SearchItem(BaseModel):
    type: str                      # 種類
    feature: Optional[str] = None  # 特徴
    lost_place: str             # 位置情報
    person: int                    # 落とし主のid
    vector: int                    # ベクトルテーブルのid


@app.post("/register_search_item/")
async def register_search_item(
    type: str = Form(...),                  # 種類
    feature: Optional[str] = Form(None),    # 特徴 
    lost_place: str = Form(...),         # 位置情報
    person: int = Form(...),               # 落とし主のID
    vector: int = Form(...),                # ベクトルテーブルのid
):
    
    # SearchItem を自分で組み立てる
    search_item = SearchItem(
        type=type,
        feature=feature,
        lost_place=lost_place,
        person=person,
        vector=vector
    )

    # よくわからんからとりあえず変数にした
    return_flag=0
    
    # DB接続
    conn = sqlite3.connect(FILE)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    cursor = conn.cursor()


    try:
        # DBにデータを挿入
        cursor.execute('''
        INSERT INTO search (type, feature, lost_place, lost_person,
                            return_flag, vector)
        VALUES (?, ?, ?, ?, ?, ?)
        ''',  
        (search_item.type, search_item.feature, search_item.lost_place, search_item.person, return_flag, vector))

        # idを取得
        inserted_id = cursor.lastrowid
        conn.commit()

        return {
            "status": "SUCCESS",
            "message": "Lost item registered successfully",
            "db_item_id": inserted_id,
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "message": f"failed to register Lost item {str(e)}",
            "db_item_id": None,
        }
    
    finally:
        conn.close()


class Receipt_Request(BaseModel):
    user_id: int                      # ユーザid
    lost_id: int                      # 落とし物id

@app.post("/receipt_request/")
async def receipt_request(
    user_id: int = Form(...),                  # ユーザid
    lost_id: int =Form(...)                    # 落とし物id
):
    
    # SearchItem を自分で組み立てる
    receipt_request = Receipt_Request(
        user_id=user_id,
        lost_id=lost_id
    )
    
    # DB接続
    conn = sqlite3.connect(FILE)
    cursor = conn.cursor()


    try:
        # DBにデータを挿入
        cursor.execute('''
        INSERT INTO receipt_request (user_id, lost_item_id)
        VALUES (?, ?)
        ''',  
        (receipt_request.user_id, receipt_request.lost_id))

        # idを取得
        inserted_id = cursor.lastrowid
        conn.commit()

        return {
            "status": "SUCCESS",
            "message": "返却依頼を追加できました",
            "db_item_id": inserted_id,
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "message": f"返却依頼の追加に失敗 {str(e)}",
            "db_item_id": None,
        }
    
    finally:
        conn.close()

