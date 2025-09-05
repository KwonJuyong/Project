
"""
💙 데이터 베이스 연결 💙
SQLAlchemy는 Engine을 사용하여 데이터베이스와 연결한다.  
우리는 with를 통해 Connection 객체를 생성하고 관리한다.

🤍conn.execute🤍
engine은 Connection 객체(==conn)를 만들어서 db를 execute(실행)한다. 
conn.excute()는 text(), select(), insert(), update()와 같은 SQLAlchemy의 객체만을 인자로 받는다.

🤍with🤍
conn 객체를 만들 때는 리소스 관리를 위해 with를 사용하는 것을 권장한다.

🧀❤️❤️🩷💛💚💙🩵💜🤍💦
"""

# db 연결
from sqlalchemy import create_engine, text
engine = create_engine("sqlite+pysqlite:///:memory:")

# 1. with 사용 (권장) - 자동으로 db 연결 해제
print("⭕ with 사용 ⭕")
with engine.connect() as conn: 
    result = conn.execute(text("SELECT 'hello world'"))
    print(result.all())

# 2. with 사용 안함 - 수동으로 연결을 생성하고 직접 close를 통해 연결을 끊어줘야한다.
print("❌ with 사용 ❌")
conn = engine.connect()
try:
    result = conn.execute(text("SELECT 'hello world'"))
    print(result.all())
finally:
    conn.close() 