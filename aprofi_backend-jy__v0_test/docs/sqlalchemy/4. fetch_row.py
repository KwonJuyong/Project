
"""
💙 선택된 행을 가져오는 4가지 방법 💙

🤍Tuple Assignment🤍
: 데이터베이스에서 가져온 행을 튜플로 받아서 각 값을 변수에 직접 할당합니다.  
- result = conn.execute(text("select x, y from some_table"))
- for x, y in result 

🤍Integer Index (권장 X)🤍
: 튜플은 인덱스로 접근이 가능합니다. 
- result = conn.execute(text("select x, y from some_table"))
- for row in result:
-     x = row[0]

🤍Attribute Name🤍
: 데이터베이스의 행은 Result 객체로 튜플처럼 동작하면서도 컬럼명으로 접근 가능합니다. 
- result = conn.execute(text("select x, y from some_table"))
- for row in result:
-     y = row.y

🤍Mapping Access (2.0 최신 스타일)🤍
: dict 형식으로 행을 mapping 후 접근한다. 
: 이는 동적으로 행에 접근하는 것이 가능하다. 
- result = conn.execute(text("select x, y from some_table"))
- for dict_row in result.mappings():
-     x = dict_row["x"]
-     y = dict_row["y"]

- columns = ["x", "y"]
- for dict_row in result.mappings():
-     for col in columns:
-         print(dict_row[col])

🧀❤️❤️🩷💛💚💙🩵💜🤍💦
"""

from sqlalchemy import create_engine, text
engine = create_engine("sqlite+pysqlite:///:memory:")

with engine.begin() as conn:
    conn.execute(text("CREATE TABLE some_table (x int, y int)"))
    conn.execute(text("INSERT INTO some_table (x, y) VALUES (:x, :y)"), 
                 [{"x": 1, "y": 1},{"x": 10, "y": 10},{"x": 100, "y": 100} ],)

# Tuple Assignment
print("💚tuple assignment")
with engine.begin() as conn:
    result = conn.execute(text("SELECT x, y FROM some_table"))
    for x, y in result:
        print(f"x: {x}  y: {y}")

# Integer Index
print("💚Integer Index")
with engine.begin() as conn:
    result = conn.execute(text("SELECT x, y FROM some_table"))
    for row in result:
        print(f"x: {row[0]}  y: {row[1]}")

# Attribute Name
print("💚Attribute Name")
with engine.begin() as conn:
    result = conn.execute(text("SELECT x, y FROM some_table"))
    for row in result:
        print(f"x: {row.x}  y: {row.y}")

# Mapping Access1
print("💚Mapping Access")
with engine.begin() as conn:
    result = conn.execute(text("SELECT x, y FROM some_table")).mappings()
    for row in result:
        print(f"x: {row['x']}  y: {row['y']}")

        
# Mapping Access 컬럼 동적 처리 가능
print("💚Mapping Access 컬럼 동적 처리")
columns = ["x", "y"]
with engine.begin() as conn:
    result = conn.execute(text("SELECT x, y FROM some_table")).mappings()
    for row in result:
        for col in columns:
            print(f"{col}: {row[col]} ", end= " ")
        print()