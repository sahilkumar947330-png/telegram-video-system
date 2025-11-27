import sqlite3
from difflib import SequenceMatcher


# =========================
# DB INIT — ek baar run hoga
# =========================
def init_db():
    conn = sqlite3.connect("videos.db")
    c = conn.cursor()

    # movies / clips
    c.execute("""CREATE TABLE IF NOT EXISTS contents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        keyword TEXT,
        token TEXT UNIQUE
    )""")

    # each file for movie (multiple qualities allowed)
    c.execute("""CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content_id INTEGER,
        file_id TEXT,
        FOREIGN KEY(content_id) REFERENCES contents(id)
    )""")

    conn.commit()
    conn.close()



# =========================
# CONTENT SAVE / GET
# =========================

def save_content(title, keyword, token):
    """movie / series / video title INSERT"""
    conn = sqlite3.connect("videos.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO contents (title, keyword, token) VALUES (?, ?, ?)",
        (title, keyword, token),
    )
    conn.commit()
    content_id = c.lastrowid
    conn.close()
    return content_id



def save_file(content_id, file_id):
    """har video file store"""
    conn = sqlite3.connect("videos.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO files (content_id, file_id) VALUES (?, ?)",
        (content_id, file_id),
    )
    conn.commit()
    conn.close()



def get_content_by_token(token):
    """cobra bot deep link ke token se content load"""
    conn = sqlite3.connect("videos.db")
    c = conn.cursor()
    c.execute(
        "SELECT id, title, keyword FROM contents WHERE token = ?",
        (token,),
    )
    row = c.fetchone()
    conn.close()

    if row:
        return {"id": row[0], "title": row[1], "keyword": row[2]}
    return None



def get_files_for_content(content_id):
    """given content ID -> multiple video files extract"""
    conn = sqlite3.connect("videos.db")
    c = conn.cursor()
    c.execute(
        "SELECT file_id FROM files WHERE content_id = ?",
        (content_id,),
    )
    rows = c.fetchall()
    conn.close()

    return [{"file_id": r[0]} for r in rows]




# =========================
# FUZZY SEARCH LOGIC (helper bot)
# =========================

def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def search_contents(query: str, limit: int = 5):
    """
    fuzzy search:
    - partial match
    - spelling mistake tolerance
    - case insensitive
    - returns top results
    """

    q = (query or "").lower().strip()
    if not q:
        return []

    conn = sqlite3.connect("videos.db")
    c = conn.cursor()
    c.execute("SELECT title, keyword, token FROM contents")
    rows = c.fetchall()
    conn.close()

    scored = []
    for title, keyword, token in rows:

        title_l = (title or "").lower()
        keyword_l = (keyword or "").lower()

        # direct substring match = BEST
        if q in keyword_l or q in title_l:
            score = 1.0
        else:
            # fuzzy similarity
            score = max(_similar(q, keyword_l), _similar(q, title_l))

        # too low score -> reject
        if score >= 0.4:
            scored.append(
                {
                    "title": title,
                    "keyword": keyword,
                    "token": token,
                    "score": score,
                }
            )

    # sort highest score first
    scored.sort(key=lambda x: x["score"], reverse=True)

    return scored[:limit]
