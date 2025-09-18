
"""
💙 트랜잭션과 커밋 💙
conn.execute로 실행한 코드는 자동으로 커밋(db에 저장)되지 않는다. 
따라서 conn.commit() 메서드를 사용하여 트랜잭션을 커밋한다.
참고, insert를 진행할때는 바인딩 변수를 사용하는 것이 보안이나 최적화 면에서 유리하다. 

🤍트랜잭션(transaction)🤍 
: SQL 쿼리를 논리적으로 묶은 것. (즉, SQL 쿼리들의 묶음)
: 이 트랜잭션이 잘 실행 된다면, commit을 통해 db에 저장
: 이 트랜잭션이 잘 실행 되지 않는다면, rollback을 통해 db에 저장 X.

🤍트랜잭션을 커밋하는 두 가지 방법🤍 
- commit as you go 🆚 begin once(권장)
: commit as you go: engine.connect(), 트랜잭션이 종료되면 commit 명시적으로 호출. 호출 안 하면 자동 rollback
: begin once: engine.begin(), 트랜잭션이 종료되면 자동 커밋. 예외 발생 시 자동 rollback.

🤍바인딩 변수🤍
: SQL 쿼리에 직접 데이터를 삽입하는 방식은 위험하다(SQL Injection) 
- conn.execute(text(f"INSERT INTO some_table (x, y) VALUES ({x}, {y})"))

: 바인딩 변수(:변수명)를 사용하면 값을 안전하게 동적으로 바인딩 할 수 있고, SQL 실행속도도 최적화 되며, 가독성도 좋아진다.
- text("INSERT INTO some_table1 (x, y) VALUES (:x, :y)"), {"x": 1, "y": 1}, ) #  값 1개
- text("INSERT INTO some_table1 (x, y) VALUES (:x, :y)"), [{"x": 1, "y": 1}, {"x": 2, "y": 4}], ) # 여러 개 값은 리스트로 묶으면 된다. 


🧀❤️❤️🩷💛💚💙🩵💜🤍💦
"""

from sqlalchemy import create_engine, text
engine = create_engine("sqlite+pysqlite:///:memory:")

# 데이터 삽입 및 커밋 (commit as you go)
with engine.connect() as conn:
    conn.execute(text("CREATE TABLE some_table1 (x int, y int)"))
    conn.execute(
        text("INSERT INTO some_table1 (x, y) VALUES (:x, :y)"),
        [{"x": 1, "y": 1}, {"x": 2, "y": 4}],
    )
    conn.commit()
    
# 데이터 조회
print("💚 commit as you go를 사용해, some_table1 테이블 접근") 
with engine.connect() as conn:
    result = conn.execute(text("SELECT * FROM some_table1"))
    print(result.all())

# 데이터 삽입 및 커밋 (begin once)
with engine.begin() as conn:
    conn.execute(text("CREATE TABLE some_table2 (x int, y int)"))
    conn.execute(
        text("INSERT INTO some_table2 (x, y) VALUES (:x, :y)"),
        [{"x": 10, "y": 10}, {"x": 20, "y": 40}],
    )
    
# 데이터 조회
print("💚 begin once를 사용해, some_table2 테이블 접근") 
with engine.begin() as conn:
    result = conn.execute(text("SELECT * FROM some_table2"))
    print(result.all())