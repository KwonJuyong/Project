from typing import Union, Literal, Annotated
from pydantic import Field

from app.problem.schemas import (
    CodingProblemRequest, CodingProblemResponseGet, UpdateCodingProblemRequest
)
from app.problem.schemas import (
    MultipleChoiceProblemResponseGet, UpdateMultipleChoiceProblemRequest, multipleChoiceRequest
)
from app.problem.schemas import (
    ShortAnswerProblemRequest, ShortAnswerProblemResponseGet, UpdateShortAnswerProblemRequest
)
from app.problem.schemas import (
    SubjectiveProblemRequest, SubjectiveProblemResponseGet, UpdateSubjectiveProblemRequest
)

createProblemRequestUnion = Annotated[
    Union[
        CodingProblemRequest,
        multipleChoiceRequest,
        ShortAnswerProblemRequest,
        SubjectiveProblemRequest,
    ],
    Field(discriminator="problemType")
]

# 수정용
UpdateProblemRequestUnion = Annotated[
    Union[
        UpdateCodingProblemRequest,
        UpdateMultipleChoiceProblemRequest,
        UpdateShortAnswerProblemRequest,
        UpdateSubjectiveProblemRequest,
    ],
    Field(discriminator="problemType")
]

# 조회용 (Response는 discriminator 없어도 무방)
GetProblemResponseUnion = Union[
    CodingProblemResponseGet,
    MultipleChoiceProblemResponseGet,
    ShortAnswerProblemResponseGet,
    SubjectiveProblemResponseGet
]