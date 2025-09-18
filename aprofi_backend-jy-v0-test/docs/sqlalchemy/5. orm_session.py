
"""
💙Connection이 아닌 Session을 사용하자!💙

🤍Connection🤍
: Connection은 직접 데이터베이스와 연결을 생성한다. 
: 트랜잭션을 수동으로 관리하며, 명시적으로 관리하고 싶다면 conn.begin()을 사용한다. 
: 단순 SQL문을 실행할 때는 Connection을 사용한다. 

🤍Session (권장)🤍
: Sessoin은 ORM에서 트랜잭션과 데이터 관리를 자동으로 처리한다. 
: ORM을 사용시 Session을 사용해야한다. 
: commit as you go 방식을 지원한다.
"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

engine = create_engine("sqlite+pysqlite:///:memory:")

with Session(engine) as session:
    session.execute(text("CREATE TABLE some_table (x int, y int)"))
    session.execute(text("INSERT INTO some_tafg78ble (x, y) VALUES (:x, :y)"), 
                 [{"x": 1, "y": 1},{"x": 10, "y": 10},{"x": 100, "y": 100} ],)
    session.commit()

with Session(engine) as session:
    result = session.execute(
        text("UPDATE some_table SET y=:y"),
        [{"y": 11}, {"y": 15}],
    )
    session.commit()

with Session(engine) as session:
    result = session.execute(text("SELECT x, y FROM some_table WHERE y > :y"), {"y": 6}).mappings()
    for row in result:
        print(f"x: {row['x']}  y: {row['y']}")
