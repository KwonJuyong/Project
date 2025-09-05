from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql import func
from sqlalchemy import update, desc, and_

from datetime import datetime
from typing import List, Dict, Tuple
from app.problem_ref.schemas import ProblemReferenceGetRequest, ProblemShowResponse
from ..models.problem_ref import ProblemReference
from app.problem.models.problem import Problem
from app.submission.models.submisson import Submission


async def bulk_create_problem_refs(
    db: AsyncSession,
    group_id: int,
    workbook_id: int,
    problem_ids: list[int],
    points: int | None = None
):
    for problem_id in problem_ids:
        new_ref = ProblemReference(
            problem_id=problem_id,
            group_id=group_id,
            workbook_id=workbook_id,
            points=points
        )
        db.add(new_ref)

    await db.commit()


async def get_problem_ref_by_ids(
        db: AsyncSession,
        group_id: int,
        workbook_id: int,
        problem_id: int
):
    statement = (
        select(ProblemReference)
        .where(
            (ProblemReference.group_id == group_id) &
            (ProblemReference.workbook_id == workbook_id) &
            (ProblemReference.problem_id == problem_id) &  
            (ProblemReference.deleted_at.is_(None))
        )
        .order_by(desc(ProblemReference.problem_reference_id))  # ← 최신 것이 위로 오도록 정렬
        .limit(1)
    )
    results = await db.execute(statement)
    problem_ref = results.scalars().first()
    if not problem_ref:
        raise HTTPException(status_code=404, detail={
            "msg": f'Problem_ref-GET with id {problem_id} not found'
        })
    return problem_ref


async def get_problem_ref_by_ref_id(db: AsyncSession, problem_ref_id: int):
    statement = (
        select(ProblemReference)
        .where(
            (ProblemReference.problem_reference_id == problem_ref_id) &
            (ProblemReference.deleted_at.is_(None)))
        )
    results = await db.execute(statement)
    problem_ref = results.scalar()
    return problem_ref


async def get_problem_reference(db: AsyncSession, problem_id: int, group_id: int, workbook_id: int):
    """문제Reference 조회 (problem_id, group_id, workbook_id 조건으로 검색)"""
    query = select(ProblemReference).where(
        (ProblemReference.problem_id == problem_id) &
        (ProblemReference.group_id == group_id) &
        (ProblemReference.workbook_id == workbook_id) & 
        (ProblemReference.deleted_at.is_(None))
    )
    result = await db.execute(query)
    problem_ref = result.scalar_one_or_none()

    if not problem_ref:
        raise HTTPException(
            status_code=404,
            detail={
                "msg": f"문제 ID {problem_id}, 그룹 {group_id}, 워크북 {workbook_id}에 대한 참조 데이터를 찾을 수 없습니다."
            }
        )

    return problem_ref

async def get_problem_refs_by_problem_id(db: AsyncSession, problem_id: int):
    result = await db.execute(
        select(ProblemReference)
        .where(
            (ProblemReference.problem_id == problem_id) & 
            (ProblemReference.deleted_at.is_(None))
        )
    )

    result = result.scalars().all()

    return result

async def delete_problem_ref_by_ids(db: AsyncSession, group_id: int, workbook_id: int, problem_id: int):
    problem_ref = await get_problem_ref_by_ids(db, group_id, workbook_id, problem_id)

    await db.execute(
        update(ProblemReference)
        .where(ProblemReference.problem_reference_id == problem_ref.problem_reference_id)
        .values(deleted_at=func.now(), is_deleted=True)
        )
    
    await db.commit()
    return JSONResponse(status_code=200, content={
        "msg": f"그룹 {group_id}에 있는 문제지 {workbook_id}의 문제 {problem_id}가 성공적으로 삭제되었습니다."
    })
    
#________________-__________________________________________________________
#problem_ref "Get" CRUD    
async def read_problem_ref_crud(db: AsyncSession, request_data: ProblemReferenceGetRequest) -> List[ProblemShowResponse]:
    # 1) 해당 그룹/워크북의 problem_reference 모두 조회 (deleted 제외)
    pref_stmt = (
        select(ProblemReference)
        .where(
            and_(
                ProblemReference.group_id == request_data.group_id,
                ProblemReference.workbook_id == request_data.workbook_id,
                ProblemReference.deleted_at.is_(None),
            )
        )
    )
    prefs: List[ProblemReference] = (await db.execute(pref_stmt)).scalars().all()
    if not prefs:
        return []

    problem_ids = [p.problem_id for p in prefs]
    ref_ids = [p.problem_reference_id for p in prefs]

    # 2) 최신 points 선정 (problem_id단위로 created_at desc, problem_reference_id desc 우선)
    prefs_sorted = sorted(
    prefs,
    key=lambda x: (x.problem_id, x.created_at or datetime.min, x.problem_reference_id),  
    reverse=True,
)
    latest_points: Dict[int, float | None] = {}
    for pr in prefs_sorted:
        if pr.problem_id not in latest_points:
            latest_points[pr.problem_id] = pr.points

    # 3) 문제 정보 조회 (title, type, description 포함)
    prob_stmt = select(Problem).where(Problem.problem_id.in_(problem_ids))  
    prob_rows: List[Problem] = (await db.execute(prob_stmt)).scalars().all() 
    problems_by_id: Dict[int, Problem] = { p.problem_id: p for p in prob_rows }  

    # 4) attempt_count: ref_id별 distinct user_id 카운트
    att_stmt = (
        select(
            Submission.problem_reference_id,
            func.count(func.distinct(Submission.user_id)).label("attempts")
        )
        .where(Submission.problem_reference_id.in_(ref_ids))
        .group_by(Submission.problem_reference_id)
    )
    att_rows = (await db.execute(att_stmt)).all()
    attempts_by_ref_id: Dict[int, int] = {row.problem_reference_id: row.attempts for row in att_rows}

    # 5) 응답 구성 (pref 목록 순서 유지)
    resp: List[ProblemShowResponse] = []
    for pr in prefs:
        prob = problems_by_id.get(pr.problem_id)
        if not prob:
            # 해당 문제 메타가 없으면 스킵
            continue

        resp.append(
            ProblemShowResponse(
                problem_id=prob.problem_id,
                title=prob.title,
                problem_type=prob.problem_type,
                description=prob.description,
                attempt_count=attempts_by_ref_id.get(pr.problem_reference_id, 0),
                pass_count=0,  # 요구사항: 일단 0 고정
                points=latest_points.get(pr.problem_id)  # 스키마에 points가 있다면 그대로 채움
            )
        )
    return resp