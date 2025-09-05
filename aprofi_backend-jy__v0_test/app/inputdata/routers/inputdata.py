import pandas as pd
import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from typing import Annotated, List

from app.database import Base, get_db
from app.security import get_current_user
from app.inputdata.schemas import InputDataRequest
from ..crud.inputdata import create_problem

router = APIRouter(
    prefix="/inputdata"
)

@router.post("")
async def input_data_endpoint(
    input_data: InputDataRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    maker_id = current_user.get("sub")
    if not maker_id:
        raise HTTPException(status_code=400, detail="User ID not found in token")

    for problem_data in input_data.problems:
        await create_problem(db, problem_data, maker_id)

    return {"message": "Problems successfully created!"}