from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import sqlite3
from typing import List, Dict, Any

app = FastAPI()

DB_PATH = "example.db"

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
        "type", "feature", "capture_place", "manager",
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