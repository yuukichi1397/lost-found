from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
import sqlite3
import uuid
from passlib.context import CryptContext
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional, List

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
    creator_id: int # Added creator_id

class JoinGroupRequest(BaseModel):
    invitation_key: str

class RemoveMemberRequest(BaseModel):
    group_id: int
    user_id_to_remove: int

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

# New models for group listing
class UserInGroup(BaseModel):
    id: int
    username: str
    phone_number: Optional[str] = None

class GroupWithMembers(BaseModel):
    group_id: int
    group_name: str
    invitation_key: str
    address: Optional[str] = None
    creator_id: int # Added creator_id
    members: List[UserInGroup]

# --- データベース関連 ---
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

# ~~~~~~~~~~~~~~~~~~~~~~~~~~ ← DBが作られている場合は消してもいい

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
            address TEXT,
            creator_id INTEGER NOT NULL, -- Added creator_id
            FOREIGN KEY (creator_id) REFERENCES users (id) ON DELETE CASCADE
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

# ~~~~~~~~~~~~~~~~~~~~~~~~~~ ← ここまで

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
@app.post("/signup/", response_model=Token)
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
        
        # Retrieve the newly created user to get their username for token creation
        newly_created_user = conn.execute('SELECT * FROM users WHERE id = ?', (new_user_id,)).fetchone()
        conn.close()

        if not newly_created_user:
            raise HTTPException(status_code=500, detail="User creation failed unexpectedly")

        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": newly_created_user['username']}, expires_delta=access_token_expires
        )
        return {"access_token": access_token, "token_type": "bearer"}
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Username already registered")
    except sqlite3.Error as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

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
        cursor = conn.execute("INSERT INTO groups (group_name, invitation_key, address, creator_id) VALUES (?, ?, ?, ?)",
                              (group.group_name, invitation_key, group.address, current_user.id))
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
            address=group.address,
            creator_id=current_user.id
        )
    except sqlite3.Error as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

@app.post("/groups/join", response_model=Group)
def join_group(join_request: JoinGroupRequest, current_user: User = Depends(get_current_user)):
    conn = get_db_connection()
    try:
        # Find the group by invitation key
        group = conn.execute('SELECT * FROM groups WHERE invitation_key = ?', (join_request.invitation_key,)).fetchone()
        if not group:
            raise HTTPException(status_code=404, detail="Group not found with this invitation key")

        # Check if user is already a member of this group
        existing_membership = conn.execute('SELECT * FROM user_groups WHERE user_id = ? AND group_id = ?',
                                            (current_user.id, group['group_id'])).fetchone()
        if existing_membership:
            raise HTTPException(status_code=400, detail="User is already a member of this group")

        # Add user to the group
        conn.execute('INSERT INTO user_groups (user_id, group_id) VALUES (?, ?)',
                     (current_user.id, group['group_id']))
        conn.commit()
        conn.close()

        return Group(
            group_id=group['group_id'],
            group_name=group['group_name'],
            invitation_key=group['invitation_key'],
            address=group['address'],
            creator_id=group['creator_id']
        )
    except sqlite3.Error as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

@app.get("/groups/my", response_model=List[GroupWithMembers])
def get_my_groups(current_user: User = Depends(get_current_user)):
    conn = get_db_connection()
    my_groups = []
    try:
        # Get all group_ids the current user belongs to
        user_group_memberships = conn.execute('SELECT group_id FROM user_groups WHERE user_id = ?',
                                                (current_user.id,)).fetchall()
        
        for membership in user_group_memberships:
            group_id = membership['group_id']
            
            # Get group details
            group_details = conn.execute('SELECT * FROM groups WHERE group_id = ?', (group_id,)).fetchone()
            if not group_details: # Should not happen if data integrity is maintained
                continue

            # Get all members of this group
            group_members = []
            member_ids = conn.execute('SELECT user_id FROM user_groups WHERE group_id = ?', (group_id,)).fetchall()
            for member_id_row in member_ids:
                member_user_id = member_id_row['user_id']
                member_details = conn.execute('SELECT id, username, phone_number FROM users WHERE id = ?',
                                                (member_user_id,)).fetchone()
                if member_details:
                    group_members.append(UserInGroup(
                        id=member_details['id'],
                        username=member_details['username'],
                        phone_number=member_details['phone_number']
                    ))
            
            my_groups.append(GroupWithMembers(
                group_id=group_details['group_id'],
                group_name=group_details['group_name'],
                invitation_key=group_details['invitation_key'],
                address=group_details['address'],
                creator_id=group_details['creator_id'],
                members=group_members
            ))
        
        conn.close()
        return my_groups
    except sqlite3.Error as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

@app.post("/groups/remove_member", response_model=dict)
def remove_member_from_group(request: RemoveMemberRequest, current_user: User = Depends(get_current_user)):
    conn = get_db_connection()
    try:
        group = conn.execute('SELECT * FROM groups WHERE group_id = ?', (request.group_id,)).fetchone()
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")

        # Authorization check
        if current_user.id != request.user_id_to_remove and current_user.id != group['creator_id']:
            raise HTTPException(status_code=403, detail="Not authorized to remove this member")

        # Check if the user to remove is actually in the group
        existing_membership = conn.execute('SELECT * FROM user_groups WHERE user_id = ? AND group_id = ?',
                                            (request.user_id_to_remove, request.group_id)).fetchone()
        if not existing_membership:
            raise HTTPException(status_code=404, detail="User is not a member of this group")

        # Remove the member
        conn.execute('DELETE FROM user_groups WHERE user_id = ? AND group_id = ?',
                     (request.user_id_to_remove, request.group_id))
        conn.commit()
        conn.close()

        return {"message": "Member removed successfully"}
    except sqlite3.Error as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
