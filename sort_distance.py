from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
from math import radians, cos, sin, sqrt, atan2
from typing import List, Dict

app = FastAPI()
db_path = "example.db"

# CORS設定（Reactと通信するために必要）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 必要に応じてフロントのURLだけに制限
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 距離を計算する関数（haversine）
def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371.0  # 地球の半径 km
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

# 物の種類の絞り込みをした後にソートできるように /物の種類のid/ソート方法のid/現在地の緯度経度/
# /lost_items/nearby?lat=34.5&lon=135.6&type_id
@app.get("/lost_items/search")
def get_lost_items_nearby(
    lat: float = Query(None, description="現在地の緯度"),
    lon: float = Query(None, description="現在地の経度"),
    type: str = Query(None, description="落とし物の種類")
) -> List[Dict]:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if type == None:
        cursor.execute("SELECT id, type, feature, capture_place, picture_path FROM lost WHERE capture_place IS NOT NULL") 
    else:
        cursor.execute('''
        SELECT id, type, feature, capture_place, picture_path
        FROM lost
        WHERE type = ?
        ''', (type,))
    items = cursor.fetchall()
    conn.close()

    results = []

    if lat == None or lon == None:
        for row in items:
            results.append({
                "id": row[0],
                "type": row[1],
                "feature": row[2],
                "capture_place": row[3],
                "picture_path": row[4]
            })
    else:
        for item in items:
            try:
                cap_lat, cap_lon = map(float, item[3].split(','))
                distance = haversine_distance(lat, lon, cap_lat, cap_lon)
                results.append({
                    "id": item[0],
                    "type": item[1],
                    "feature": item[2],
                    "capture_place": item[3],
                    "distance_km": round(distance, 3)
                })
            except Exception as e:
                print(f"Invalid capture_place for id={item[0]}: {e}")

        # 距離で昇順ソート
        results.sort(key=lambda x: x["distance_km"])

    return results

# テスト方法

# lat 現在地の緯度
# lon 現在地の経度
# type 物の種類　例：傘、バッグ、財布など

# 全てを距離順でソート
# curl -G "http://localhost:8000/lost_items/search" --data-urlencode "lat=34.5" --data-urlencode "lon=135.6"

# 文字(type)で検索　
# curl -G "http://localhost:8000/lost_items/search" --data-urlencode "type=傘"

# 文字(type)で検索して、距離順にソート　例：傘とか財布とか
# curl -G "http://localhost:8000/lost_items/search" --data-urlencode "lat=34.5" --data-urlencode "lon=135.6" --data-urlencode "type=傘"

# 全てを表示
# curl -G "http://localhost:8000/lost_items/search"

# 注意！
# "lat"と"lon"のどちらかしかない場合は、ソートせずに表示します
# 例：curl -G "http://localhost:8000/lost_items/search" --data-urlencode "lat=34.5" --data-urlencode "type_id=傘"