import json
from pathlib import Path

import aiosqlite


class UserStore:
  def __init__(self, database: Path):
    self.database = database

  async def initialize(self) -> None:
    self.database.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(self.database) as db:
      await db.execute("PRAGMA journal_mode=WAL")
      await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
          telegram_id INTEGER PRIMARY KEY,
          status TEXT NOT NULL,
          modules_json TEXT NOT NULL,
          error TEXT,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
      """)
      await db.commit()

  async def set(self, telegram_id: int, status: str, modules: list[str], error: str | None = None) -> None:
    async with aiosqlite.connect(self.database) as db:
      await db.execute(
        """INSERT INTO users (telegram_id, status, modules_json, error, updated_at)
           VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(telegram_id) DO UPDATE SET
             status=excluded.status,
             modules_json=excluded.modules_json,
             error=excluded.error,
             updated_at=CURRENT_TIMESTAMP""",
        (telegram_id, status, json.dumps(modules), error),
      )
      await db.commit()

  async def get(self, telegram_id: int) -> dict | None:
    async with aiosqlite.connect(self.database) as db:
      db.row_factory = aiosqlite.Row
      async with db.execute(
        "SELECT telegram_id, status, modules_json, error, updated_at FROM users WHERE telegram_id=?",
        (telegram_id,),
      ) as cursor:
        row = await cursor.fetchone()
    if row is None:
      return None
    return {
      "telegram_id": row["telegram_id"],
      "status": row["status"],
      "modules": json.loads(row["modules_json"]),
      "error": row["error"],
      "updated_at": row["updated_at"],
    }
