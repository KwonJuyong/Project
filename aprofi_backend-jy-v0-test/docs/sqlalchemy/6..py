
"""
💙💙
🤍
💚
🧀❤️❤️🩷💛💚💙🩵💜🤍💦
"""

from sqlalchemy import create_engine, text
engine = create_engine("sqlite+pysqlite:///:memory:")

with engine.begin() as conn:
    result = conn.execute(text("SELECT x, y FROM some_table"))
    for row in result:
        print(f"x: {row.x}  y: {row.y}")