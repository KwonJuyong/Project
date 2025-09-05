import logging
from contextlib import asynccontextmanager
from fastapi.encoders import jsonable_encoder
from app.database import get_db
from fastapi.responses import JSONResponse
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql import func, and_
from sqlalchemy.orm import with_polymorphic
from typing import Annotated, List, Union
from app.problem.crud.problem import get_problem_by_id
from ..models.problem import Problem
from ..models.coding_problem import CodingProblem
from ..models.multiple_choice_problem import MultipleChoiceProblem
from ..models.short_answer_problem import ShortAnswerProblem
from ..models.subjective_problem import SubjectiveProblem
from app.group.models.group_member import GroupUser
from app.problem_ref.models.problem_ref import ProblemReference
from ..schemas import ProblemTypeEnum, CodingProblemRequest, CodingProblemResponse, multipleChoiceRequest, MultipleChoiceResponse, ShortAnswerProblemRequest, ShortAnswerProblemResponse, SubjectiveProblemRequest, SubjectiveProblemResponse \
    , CodingProblemResponseGet, MultipleChoiceProblemResponseGet, ShortAnswerProblemResponseGet, SubjectiveProblemResponseGet, ShortAnswerRatingModeEnum
from app.security import get_current_user
from ..crud.problem import create_coding_problem, create_multiple_choice_problem, create_short_answer_problem, create_subjective_problem, transform_problem_to_response, get_problem_by_id, delete_problem, soft_delete_problem, create_problem_instance_from_update, normalize_problem_type
from ..problem_type_Union import createProblemRequestUnion, GetProblemResponseUnion, UpdateProblemRequestUnion
from ..models.problem import ProblemTypeEnum as ModelProblemTypeEnum

router = APIRouter(
    prefix="/problems"
)
logger = logging.getLogger(__name__)


#하나의 작업 단위가 완전하게 성공하거나, 실패 시 모두 되돌리는 것(rollback)
@asynccontextmanager
async def transaction(db: AsyncSession):
    """트랜잭션 컨텍스트 매니저"""
    try:
        yield db
        await db.commit()
    except Exception:
        await db.rollback()
        raise
#____________________________________________________________________________________

@router.post("")
async def create_problem_endpoint(
    problem: Annotated[
        createProblemRequestUnion,
        Body(discriminator="problemType")
    ],
    current_user: Annotated[dict, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    match problem.problemType:
        case ProblemTypeEnum.coding | ProblemTypeEnum.debugging:
            return await handle_coding_problem(problem, current_user, db)
        case ProblemTypeEnum.multiple_choice:
            return await handle_multiple_choice_problem(problem, current_user, db)
        case ProblemTypeEnum.short_answer:
            return await handle_short_answer_problem(problem, current_user, db)
        case ProblemTypeEnum.subjective:
            return await handle_subjective_problem(problem, current_user, db)
        case _:
            raise HTTPException(status_code=400, detail="유효하지 않은 문제 유형입니다.")

KOR_TO_ENG_PROBLEM_TYPE = {
    "코딩": "coding",
    "객관식": "multiple_choice",
    "단답형": "short_answer",
    "주관식": "subjective",
    "디버깅": "debugging"
}

async def handle_coding_problem(problem: CodingProblemRequest, user: dict, db: AsyncSession) -> CodingProblemResponse:
    data = problem.model_dump()
    data["maker_id"] = user["sub"]
    #데이터를 받아와서 Enum으로 변환
    #문제 유형을 Enum으로 변환 -> ProblemType은 Enum이므로, value로 변환 -> problemType은 안쓰기때문에 pop처리 (내가 원하는건 problem_type)
    data["problem_type"] = KOR_TO_ENG_PROBLEM_TYPE[problem.problemType]
    data.pop("problemType", None)
    data["rating_mode"] = problem.rating_mode.value
    data["reference_codes"] = [rc.model_dump() for rc in problem.reference_codes]
    data["test_cases"] = [tc.model_dump() for tc in problem.test_cases]
    data["base_code"] = [bc.model_dump() for bc in problem.base_code]

    orm_problem = CodingProblem(**data)
    created = await create_coding_problem(db, orm_problem)
    return CodingProblemResponse(
        problem_id=created.problem_id,
        maker_id=created.maker_id,
        title=created.title,
        description=created.description,
        difficulty=created.difficulty,
        tags=created.tags,
        problem_condition=created.problem_condition,
        created_at=created.created_at,
        problemType=created.problem_type.value,
        rating_mode=created.rating_mode,
        reference_codes=created.reference_codes,
        test_cases=created.test_cases or [], 
        base_code=created.base_code or []
    )
async def handle_multiple_choice_problem(problem: multipleChoiceRequest, user: dict, db: AsyncSession) -> MultipleChoiceResponse:
    data = problem.model_dump()
    data["maker_id"] = user["sub"]
    data["problem_type"] = KOR_TO_ENG_PROBLEM_TYPE[problem.problemType]
    data.pop("problemType", None)
    data["options"] = problem.options
    data["correct_answers"] = problem.correct_answers
    
    orm_problem = MultipleChoiceProblem(**data)
    created = await create_multiple_choice_problem(db, orm_problem)
    return MultipleChoiceResponse(
        problem_id=created.problem_id,
        maker_id=created.maker_id,
        title=created.title,
        description=created.description,
        difficulty=created.difficulty,
        tags=created.tags,
        created_at=created.created_at,
        problemType=created.problem_type,
        options=created.options,
        correct_answers=created.correct_answers,
        rating_mode=created.rating_mode
    )

async def handle_short_answer_problem(problem: ShortAnswerProblemRequest, user: dict, db: AsyncSession) -> ShortAnswerProblemResponse:
    data = problem.model_dump()
    data["maker_id"] = user["sub"]
    data["problem_type"] = KOR_TO_ENG_PROBLEM_TYPE[problem.problemType]
    data.pop("problemType", None)
    data["rating_mode"] = problem.rating_mode.value

    orm_problem = ShortAnswerProblem(**data)
    created = await create_short_answer_problem(db, orm_problem)
    return ShortAnswerProblemResponse(
        problem_id=created.problem_id,
        maker_id=created.maker_id,
        title=created.title,
        description=created.description,
        difficulty=created.difficulty,
        tags=created.tags,
        created_at=created.created_at,
        problemType=created.problem_type.value,
        rating_mode=ShortAnswerRatingModeEnum(created.rating_mode),
        answer_text=created.answer_text,
        grading_criteria=created.grading_criteria,
    )
async def handle_subjective_problem(problem: SubjectiveProblemRequest, user: dict, db: AsyncSession) -> SubjectiveProblemResponse:
    data = problem.model_dump()
    data["maker_id"] = user["sub"]
    data["problem_type"] = KOR_TO_ENG_PROBLEM_TYPE[problem.problemType]
    data.pop("problemType", None)
    data["rating_mode"] = problem.rating_mode.value

    orm_problem = SubjectiveProblem(**data)
    created = await create_subjective_problem(db, orm_problem)
    return SubjectiveProblemResponse(
        problem_id=created.problem_id,
        maker_id=created.maker_id,
        title=created.title,
        description=created.description,
        difficulty=created.difficulty,
        tags=created.tags,
        created_at=created.created_at,
        problemType=created.problem_type.value,
        rating_mode=created.rating_mode,
        answer_text=created.answer_text,
        grading_criteria=created.grading_criteria,
    )

#_______________________________________________________________________________

@router.get("/me", response_model=List[GetProblemResponseUnion])
async def read_problems_endpoint(
    current_user: Annotated[dict, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    try:
        ProblemPoly = with_polymorphic(Problem, "*")
        
        statement = select(ProblemPoly).where(
            (Problem.maker_id == current_user["sub"]) &
            (Problem.deleted_at.is_(None))
        )
        results = await db.execute(statement)
        problems = results.scalars().all()
        
        response_list = [transform_problem_to_response(p) for p in problems]
        return response_list

    except Exception as e:
        logger.exception("[문제 조회 실패]")
        raise HTTPException(status_code=500, detail=str(e))
#__________________________________________________________________________________


@router.get("/{problem_id}", response_model=GetProblemResponseUnion)
async def read_problem_by_id_endpoint(
        problem_id: int,
        current_user: Annotated[dict, Depends(get_current_user)],
        db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Problem).where(Problem.problem_id == problem_id))
    problem = result.scalar_one_or_none()

    if not problem:
        raise HTTPException(status_code=404, detail="문제를 찾을 수 없습니다.")
    if problem.maker_id != current_user["sub"]:
        raise HTTPException(status_code=403, detail="접근 권한 없음")

    return transform_problem_to_response(problem)

#______________________________________________________________________________________________

@router.get("/{group_id}/{workbook_id}/{problem_id}", response_model=GetProblemResponseUnion)
async def get_problem_from_group_workbook(
    group_id: int,
    workbook_id: int,
    problem_id: int,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    try:
        async with db.begin():
            # 1. 그룹에 소속된 멤버인지 확인
            member_result = await db.execute(
                select(GroupUser.user_id).where(GroupUser.group_id == group_id)
            )
            user_ids = member_result.scalars().all()
            if current_user["sub"] not in user_ids:
                raise HTTPException(status_code=403, detail="해당 그룹에 소속된 사용자가 아닙니다.")

            # 2. 해당 문제(ref)가 group + workbook에 연결되어 있는지 확인
            ref_result = await db.execute(
                select(ProblemReference).where(
                    ProblemReference.group_id == group_id,
                    ProblemReference.workbook_id == workbook_id,
                    ProblemReference.problem_id == problem_id
                )
            )
            problem_ref = ref_result.scalar_one_or_none()
            if not problem_ref:
                raise HTTPException(status_code=404, detail="문제집에 해당 문제가 존재하지 않습니다.")

            # 3. 문제 자체 조회
            result = await db.execute(
                select(Problem).where(Problem.problem_id == problem_id)
            )
            problem = result.scalar_one_or_none()
            if not problem:
                raise HTTPException(status_code=404, detail="문제를 찾을 수 없습니다.")

        # 4. 변환 함수 호출 (문제 유형에 따라 동적 응답)
        return transform_problem_to_response(problem)

    except HTTPException:
        raise  # FastAPI가 자동 처리
    except Exception as e:
        logger.error(f"[문제 조회 실패] {str(e)}")
        raise HTTPException(status_code=500, detail="내부 서버 오류 발생")

#______________________________________________________________________________________________



@router.put("/{problem_id}")
async def update_problem_endpoint(
    problem_id: int,
    updates: UpdateProblemRequestUnion,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    try:
        # 1. 기존 문제 조회 및 권한 확인
        old_problem = await get_problem_by_id(db, problem_id)
        if old_problem.maker_id != current_user["sub"]:
            raise HTTPException(status_code=403, detail="문제 수정 권한이 없습니다.")

        # 2. 기존 문제 soft delete
        await soft_delete_problem(db, problem_id)

        # 3. 새로운 문제 생성 준비
        new_problem = create_problem_instance_from_update(old_problem, updates)

        # 4. 새 문제 insert
        db.add(new_problem)
        await db.commit()
        await db.refresh(new_problem)

        # 5. 응답 변환 및 반환
        return transform_problem_to_response(new_problem)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[문제 수정 실패] {e}")
        raise HTTPException(status_code=500, detail="문제 수정 중 오류 발생")
    
    
@router.delete("/{problem_id}")
async def delete_problem_endpoint(
        problem_id: int,
        current_user: Annotated[dict, Depends(get_current_user)],
        db: AsyncSession = Depends(get_db)
):
    existing_problem = await get_problem_by_id(db, problem_id)

    if existing_problem.maker_id != current_user["sub"]:
        raise HTTPException(status_code=403, detail="You do not have permission to delete this problem")

    deleted_problem = await delete_problem(db, problem_id)
    return deleted_problem


# 라우팅 충돌 이슈
# @router.get("/stats/{problem_id}", response_model=ProblemStatsWrapper)
# async def create_problem_stats_endpoint(
#     problem_id: int,
#     current_user: Annotated[dict, Depends(get_current_user)],
#     db: AsyncSession = Depends(get_db)
# ):
#     try:
#         # 1. problem_id를 받는다. 
#         # 2. problem_id에 해당하는 
#         #    [group-workbook-좋아요-시도수-정답수]
        
#         # problem_id -> [problem_ref_id-group_id-workbook_id]
#         # problem_ref_ids 
#         # -> [slect(ProblemRefLike 행 갯수 세는 함수)
#         #     .where(ProblemRefLike.problem_ref_id == problem_ref_id))
#         #       for problem_ref_id in problem_ref_ids]

#         problem_refs = await get_problem_references_by_id(db, problem_id)
        
#         groups = [await get_group_by_group_id(db, ref.group_id) for ref in problem_refs]
#         # None | goup
        
#         workbooks = [await get_workbook_by_workbook_id(db, ref.workbook_id) for ref in problem_refs]
        
#         #problem_id가 주어졌을때, problem_ref당 like를 구해서 리스트로 반환
#         # problem_ref 가 주어졌을때, 그 애들의 like_count
#         like_counts = await get_problem_ref_like(db, problem_id)
        
#         # [{"attempt" : 4, "passed" : 1}, ...]
#         solve_stats = await get_solve_stats(db, problem_id) 
        
#         comment_dicts = await get_problem_comments(db, problem_id)

#         print(f"그룹 길이! : {len(groups)}")
#         print(f"문제지 길이! : {len(workbooks)}")
#         print(f"레퍼런스 길이! : {len(problem_refs)}")
#         print(f"좋아유 길이! : {len(like_counts)}")
#         print(f"제출 길이! : {len(solve_stats)}")
#         print(f"코멘트 길이! : {len(comment_dicts)}")
        
#         response_data = []

#         for i, (group, workbook, pr, like, solve) in enumerate(zip(groups, workbooks, problem_refs, like_counts, solve_stats)):
#             if group is None or workbook is None:
#                 continue

#             # 첫 번째 항목에만 실제 댓글 포함, 나머지는 빈 리스트
#             comments = [
#                 ProblemCommentsResponse(**c) for c in comment_dicts.get(pr.problem_id, [])
#             ] if i == 0 else []

#             response_data.append(
#                 ProblemStatsResponse(
#                     problem_id=pr.problem_id,
#                     group_id=group.group_id,
#                     group_name=group.group_name,
#                     workbook_id=workbook.workbook_id,
#                     workbook_name=workbook.workbook_name,
#                     like=like,
#                     attempt_count=solve["attempt"],
#                     pass_count=solve["passed"],
#                     comments=comments
#                 )
#             )

#         return JSONResponse(
#             status_code=200,
#             content=jsonable_encoder({
#                 "msg": "문제 통계 조회 성공",
#                 "data": response_data
#             })
#         )

#     except HTTPException as e:
#         raise e  # 발생한 HTTPException 그대로 반환
#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail={"msg": f"서버 내부 오류: {str(e)}"}
#         )