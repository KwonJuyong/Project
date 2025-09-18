# app/services/condition_utils.py
from typing import Any, Dict, List, Union, cast, Tuple, Sequence, Mapping

NumberLike = Union[int, float, str]

def _get_field(raw: object, key: str, default: Any = None) -> Any:
    if isinstance(raw, Mapping):  # dict 포함
        return raw.get(key, default)
    return getattr(raw, key, default)

def _to_int(x: Any, default: int) -> int:
    if x is None or isinstance(x, bool):
        return default
    if isinstance(x, int):
        return x
    if isinstance(x, float):
        try:
            return int(x)
        except Exception:
            return default
    if isinstance(x, str):
        s = x.strip()
        if not s:
            return default
        try:
            return int(s)
        except Exception:
            try:
                return int(float(s))
            except Exception:
                return default
    try:
        return int(cast(NumberLike, x))
    except Exception:
        return default

def _to_float(x: Any, default: float) -> float:
    if x is None or isinstance(x, bool):
        return default
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        s = x.strip()
        if not s:
            return default
        try:
            return float(s)
        except Exception:
            return default
    try:
        return float(cast(NumberLike, x))
    except Exception:
        return default

def _to_str_or_default(x: Any, default: str) -> str:
    if x is None:
        return default
    if isinstance(x, str):
        s = x.strip()
        return s if s else default
    return default

def normalize_condition_checks(checks: Sequence[object]) -> List[Dict[str, Any]]:
    """
    다양한 형태의 condition 결과를 list[dict] 스키마로 정규화한다.
    존재 키: condition/description/is_required/check_type/passed/feedback/weight(옵션)
    """
    items: List[Dict[str, Any]] = []
    for idx, raw in enumerate(checks, start=1):
        cond_raw = _get_field(raw, "condition", None)
        desc_raw = _get_field(raw, "description", None)
        req_raw  = _get_field(raw, "is_required", True)
        type_raw = _get_field(raw, "check_type", "code_analysis")
        pass_raw = _get_field(raw, "passed", False)
        fb_raw   = _get_field(raw, "feedback", "")
        wt_raw   = _get_field(raw, "weight", 1.0)

        desc = _to_str_or_default(desc_raw, _to_str_or_default(cond_raw, f"Condition {idx}"))
        item = {
            "condition": _to_int(cond_raw, idx),
            "is_required": bool(req_raw),
            "description": desc,
            "check_type": _to_str_or_default(type_raw, "code_analysis"),
            "passed": bool(pass_raw),
            "feedback": _to_str_or_default(fb_raw, ""),
            "weight": _to_float(wt_raw, 1.0),
        }
        items.append(item)
    return items

def distribute_condition_scores(items: List[Dict[str, Any]], total_points: float) -> Tuple[List[Dict[str, Any]], float]:
    """
    items에 score를 부여한다(통과 시만). 가중치 합으로 비례 배분.
    반환: (items_with_scores, earned_sum)
    """
    if not items:
        return [], 0.0

    weights_sum = sum(float(max(0.0, it.get("weight", 1.0))) for it in items) or 1.0
    # 분배 단위 점수
    per_unit = float(total_points) / float(weights_sum)

    earned_sum = 0.0
    out: List[Dict[str, Any]] = []
    for it in items:
        w = float(max(0.0, it.get("weight", 1.0)))
        allocated = round(per_unit * w, 2)  # 배정 점수(통과 시 받을 수 있는 최대)
        got = round(allocated if it.get("passed") else 0.0, 2)
        earned_sum += got
        new_it = {**it, "score": got}
        out.append(new_it)

    # 소수 반올림 누적 오차 보정(선택): 통과 항목 중 첫 항목에 미세 보정
    gap = round(float(total_points) - earned_sum, 2)
    if abs(gap) >= 0.01:
        for i, it in enumerate(out):
            if it.get("passed"):
                it["score"] = round(it["score"] + gap, 2)
                earned_sum = round(earned_sum + gap, 2)
                break

    return out, earned_sum
