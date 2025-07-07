import sqlite3
import sqlite_vec
import struct

def serialize_f32(vector):
    return struct.pack('%sf' % len(vector), *vector)

conn = sqlite3.connect('example.db')
conn.enable_load_extension(True)
sqlite_vec.load(conn)
conn.enable_load_extension(False)
cursor = conn.cursor()

# 1. users
cursor.execute("INSERT INTO users (name, password, telenum) VALUES (?, ?, ?)",
               ("yuukichi", "hashedpass", "090-1234-5678"))
cursor.execute("INSERT INTO users (name, password, telenum) VALUES (?, ?, ?)",
               ("bando", "hashedpass", "080-1234-5678"))

# 2. groups
cursor.execute("INSERT INTO groups (name, passkey, place) VALUES (?, ?, ?)",
               ("香川大学", "abc123", "135,47"))

# 3. user_groups
cursor.execute("INSERT INTO user_groups (user_id, group_id) VALUES (?, ?)", (1, 1))

# 4. vec_lost
vec1 = serialize_f32([0.1, 0.2, 0.3, 0.4])
cursor.execute("INSERT INTO vec_lost (rowid, embedding) VALUES (?, ?)", (1, vec1))

# 5. lost
cursor.execute('''
    INSERT INTO lost (type, feature, capture_place, manager, manage_group,
                      return_flag, picture_path, return_person, vector)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
''', ("傘", "青い折りたたみ", "135,47", 1, 1, 0, "images/umbrella.jpg", None, 1))

# 6. vec_search
vec2 = serialize_f32([0.1, 0.25, 0.35, 0.45])
cursor.execute("INSERT INTO vec_search (rowid, embedding) VALUES (?, ?)", (1, vec2))

# 7. search
cursor.execute('''
    INSERT INTO search (type, feature, lost_place, lost_person,
                        return_flag, picture_path, vector)
    VALUES (?, ?, ?, ?, ?, ?, ?)
''', ("傘", "青くて折り畳み傘", "135,47", 2, 0, "images/umbrella2.jpg", 1))

conn.commit()
conn.close()
