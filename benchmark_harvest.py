import sqlite3
import time
import pathlib
import os

# Set up test env
vault_dir = pathlib.Path("./benchmark_vault")
vault_dir.mkdir(exist_ok=True)
db_path = vault_dir / "Meta" / ".cache" / "memory.db"
(vault_dir / "Meta" / ".cache").mkdir(parents=True, exist_ok=True)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Create table
conn.execute("""
    CREATE TABLE IF NOT EXISTS candidates (
        id TEXT PRIMARY KEY,
        session_id TEXT,
        status TEXT,
        importance INTEGER,
        target_dir TEXT,
        title TEXT,
        content TEXT,
        source TEXT,
        vault_path TEXT
    )
""")
conn.commit()

NUM_RECORDS = 500

# Insert test data
for i in range(NUM_RECORDS):
    conn.execute("""
        INSERT INTO candidates (id, session_id, status, importance, target_dir, title, content, source)
        VALUES (?, ?, 'pending', 10, 'Ideas', ?, ?, ?)
    """, (f"id_{i}", "sess_1", f"Title {i}", f"Content {i}", f"source_{i}"))
conn.commit()

# Test performance
import scripts.harvest as harvest

# Override limit in promote_l1 so we test 500 records
original_promote_l1 = harvest.promote_l1

def patch_promote_l1(vault, conn, threshold=10):
    rows = conn.execute("""
        SELECT * FROM candidates
        WHERE status='pending' AND importance >= ? AND target_dir='Ideas'
        ORDER BY importance DESC LIMIT ?
    """, (threshold, NUM_RECORDS)).fetchall()
    count = 0
    updates = []
    for row in rows:
        try:
            title = row["title"] or harvest.extract_title(row["content"]) or "Untitled Idea"
            path = harvest.create_note(vault, "Ideas", title, row["content"],
                               tags=["#idea", "#auto"], source=row["source"])
            updates.append((str(path), row["id"]))
            count += 1
        except Exception as e:
            harvest.warn(f"L1 promote error: {e}")
    if updates:
        conn.executemany(
            "UPDATE candidates SET status='promoted', vault_path=? WHERE id=?",
            updates
        )
        conn.commit()
    return count

start_time = time.time()
patch_promote_l1(vault_dir, conn, threshold=5)
end_time = time.time()

print(f"Time taken (executemany + single commit) for {NUM_RECORDS} records: {end_time - start_time:.4f} seconds")

# Cleanup
conn.close()
import shutil
shutil.rmtree(vault_dir)
