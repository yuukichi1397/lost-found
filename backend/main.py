from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
import sqlite3
import uuid
from passlib.context import CryptContext
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional

# --- 設定 ---
DATABASE = 'users.db'
SECRET_KEY = "your-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# --- FastAPIインスタンスとミドルウェア ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- パスワードと認証の準備 ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# --- Pydanticモデル ---
class UserCreate(BaseModel):
    username: str
    password: str
    phone_number: Optional[str] = None

class User(BaseModel):
    id: int
    username: str
    phone_number: Optional[str] = None

class GroupCreate(BaseModel):
    group_name: str
    address: Optional[str] = None

class Group(BaseModel):
    group_id: int
    group_name: str
    invitation_key: str
    address: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

# --- データベース関連 ---
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def create_tables():
    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            hashed_password TEXT NOT NULL,
            phone_number TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            group_id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_name TEXT NOT NULL,
            invitation_key TEXT NOT NULL UNIQUE,
            address TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_groups (
            user_id INTEGER,
            group_id INTEGER,
            PRIMARY KEY (user_id, group_id),
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
            FOREIGN KEY (group_id) REFERENCES groups (group_id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    conn.close()

@app.on_event("startup")
def startup_event():
    create_tables()

# --- 認証関連のヘルパー関数 ---
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (token_data.username,)).fetchone()
    conn.close()
    
    if user is None:
        raise credentials_exception
    return User(id=user['id'], username=user['username'], phone_number=user['phone_number'])

# --- APIエンドポイント ---
@app.post("/signup/", response_model=User)
def create_user(user: UserCreate):
    conn = get_db_connection()
    try:
        existing_user = conn.execute('SELECT * FROM users WHERE username = ?', (user.username,)).fetchone()
        if existing_user:
            raise HTTPException(status_code=400, detail="Username already registered")

        hashed_password = get_password_hash(user.password)
        cursor = conn.execute('INSERT INTO users (username, hashed_password, phone_number) VALUES (?, ?, ?)',
                              (user.username, hashed_password, user.phone_number))
        conn.commit()
        new_user_id = cursor.lastrowid
        conn.close()
        return User(id=new_user_id, username=user.username, phone_number=user.phone_number)
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Username already registered")

@app.post("/login", response_model=Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (form_data.username,)).fetchone()
    conn.close()

    if not user or not verify_password(form_data.password, user['hashed_password']):
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user['username']}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/users/me/", response_model=User)
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

@app.post("/groups/", response_model=Group)
def create_group(group: GroupCreate, current_user: User = Depends(get_current_user)):
    invitation_key = uuid.uuid4().hex
    conn = get_db_connection()
    try:
        # Create the group
        cursor = conn.execute("INSERT INTO groups (group_name, invitation_key, address) VALUES (?, ?, ?)",
                              (group.group_name, invitation_key, group.address))
        new_group_id = cursor.lastrowid

        # Add the creator to the group
        conn.execute("INSERT INTO user_groups (user_id, group_id) VALUES (?, ?)",
                     (current_user.id, new_group_id))
        
        conn.commit()
        conn.close()

        return Group(
            group_id=new_group_id,
            group_name=group.group_name,
            invitation_key=invitation_key,
            address=group.address
        )
    except sqlite3.Error as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

@app.get("/")
def read_root():
    return {"Hello": "World"}