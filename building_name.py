import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# FastAPIアプリのインスタンスを作成
app = FastAPI()

# CORS(クロスオリジンリソース共有)ミドルウェアの設定
# これがないと、ブラウザがセキュリティエラーを出すよ
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # すべてのオリジンを許可（開発用）。本番では特定のドメインに制限してね。
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 逆ジオコーディング（緯度経度→住所）を行うエンドポイント
@app.get("/reverse-geocode/")
def reverse_geocode(lat: float, lon: float):
    """
    指定された緯度・経度から住所情報を取得する
    """
    # Nominatim APIのエンドポイントURL
    url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}"

    # Nominatimの利用ポリシーに従い、必ずUser-Agentを設定する
    headers = {
        'User-Agent': 'MyWebApp/1.0 (your-email@example.com)' # ここは自分のアプリ名や連絡先に変更してね
    }

    try:
        # APIにリクエストを送信
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # エラーがあれば例外を発生させる
        data = response.json()

        # 建物名や通りの名前などを取得
        # 'display_name' には完全な住所が入っている
        # 'address' の中に 'building', 'road', 'house_number' など個別の情報が入っている
        address = data.get('address', {})
        building_name = address.get('building', None)
        display_name = data.get('display_name', '情報が取得できませんでした')
        
        # 建物名がなければ、全体の表示名を返す
        result_name = building_name if building_name else display_name

        return {"name": result_name}

    except requests.exceptions.RequestException as e:
        # 通信エラーなど
        raise HTTPException(status_code=500, detail=f"API request failed: {e}")
    except Exception as e:
        # その他の予期せぬエラー
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")