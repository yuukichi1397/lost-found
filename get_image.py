# import os
# from fastapi import FastAPI, HTTPException
# from fastapi.responses import FileResponse

# app = FastAPI()

# # 画像が格納されているディレクトリのパス
# # __file__ はこのファイル(main.py)のパスを指す
# IMAGE_DIR = os.path.join(os.path.dirname(__file__), "images")

# @app.get("/images/{filename}")
# async def get_image(filename: str):
#     """
#     指定されたファイル名の画像を返すAPI
#     """
#     # ファイルのフルパスを生成
#     image_path = os.path.join(IMAGE_DIR, filename)

#     # 指定されたパスにファイルが存在するかチェック
#     if not os.path.isfile(image_path):
#         # ファイルが存在しない場合は404エラーを返す
#         raise HTTPException(status_code=404, detail="Image not found")

#     # FileResponseを使って画像ファイルを返す
#     return FileResponse(image_path)

import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware # これをインポート

app = FastAPI()

# --- ここからCORSミドルウェアの設定を追加 ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # すべてのオリジンからのアクセスを許可する（開発用）
    allow_credentials=True,
    allow_methods=["*"],  # すべてのHTTPメソッドを許可する
    allow_headers=["*"],  # すべてのHTTPヘッダーを許可する
)
# --- ここまで ---

# in --> ./images/画像ファイル名
@app.get("/images/{filename}")
async def get_image(filename: str):
    """
    指定されたファイル名の画像を返すAPI
    """
    # image_path = os.path.join(IMAGE_DIR, filename)
    image_path = filename

    if not os.path.isfile(image_path):
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(image_path)