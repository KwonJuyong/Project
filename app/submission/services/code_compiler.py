# app/submission/services/code_compiler.py
from __future__ import annotations
import threading
import shutil
import os
import time
import psutil
import tempfile
import subprocess
from typing import List, Dict, Any, Tuple

# 러너가 기대하는 스키마들만 import (pydantic v2)
from app.submission.schemas import (
    TestCaseInput,         # 입력: {input, expected_output}
    RunnerTestResult,      # 출력: {test_case_index, status, output, error, execution_time, memory_usage, passed, input, expected_output}
    ExecutionStatus,       # Enum: SUCCESS/TIMEOUT/ERROR
    OverallStatus,         # Enum: success/partial/failed
    RatingMode,   
    TestCase# Enum/str 유사: hard/space/regex/none 등
)

# 비교 로직
from app.submission.services.problem_Normalization import problem_Normalization


def _OS(name: str):
    """OverallStatus 멤버 안전 접근."""
    try:
        return getattr(OverallStatus, name.upper())
    except AttributeError:
        return getattr(OverallStatus, name.lower())


def _ES(name: str):
    """ExecutionStatus 멤버 안전 접근."""
    try:
        return getattr(ExecutionStatus, name.upper())
    except AttributeError:
        return getattr(ExecutionStatus, name.lower())
import threading
import time
import psutil
from typing import Tuple

def _sample_peak_rss(proc: psutil.Process, interval: float = 0.01) -> Tuple[threading.Event, threading.Thread, list[int]]:
    """
    별도 스레드에서 proc + 자식 RSS 합을 샘플링. peak[0]에 최대값을 담는다.
    사용: stop, t, peak = _sample_peak_rss(proc); ... ; stop.set(); t.join(); peak_val = peak[0]
    """
    peak = [0]
    stop = threading.Event()

    def sampler():
        while not stop.is_set():
            try:
                if not proc.is_running():
                    break
                total = 0
                with proc.oneshot():
                    try:
                        total += proc.memory_info().rss
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                    for ch in proc.children(recursive=True):
                        try:
                            total += ch.memory_info().rss
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                if total > peak[0]:
                    peak[0] = total
            except Exception:
                pass
            time.sleep(interval)

    t = threading.Thread(target=sampler, daemon=True)
    t.start()
    return stop, t, peak

class CodeRunner:
    TIMEOUT = 5  # seconds
    MEMORY_LIMIT = 512 * 1024 * 1024  # 512MB in bytes

    def __init__(self):
        self.language_configs = {
            "python": {
                "file_ext": ".py",
                "compile_cmd": None,
                "run_cmd": ["python", "{file}"],
            },
            "java": {
                "file_ext": ".java",
                "compile_cmd": ["javac", "{file}"],
                "run_cmd": ["java", "{class_name}"],
                "main_class": "Solution",
            },
            "cpp": {
                "file_ext": ".cpp",
                "compile_cmd": ["g++", "-O2", "-std=c++17", "-o", "{exe}", "{file}"],
                "run_cmd": ["./{exe}"],
            },
            "c": {
                "file_ext": ".c",
                "compile_cmd": ["gcc", "-O2", "-std=c17", "-o", "{exe}", "{file}"],
                "run_cmd": ["./{exe}"],
            },
            "javascript": {
                "file_ext": ".js",
                "compile_cmd": None,
                "run_cmd": ["node", "{file}"],
            },
        }

    # --------------------------
    # 준비/컴파일
    # --------------------------
    def _prepare_code_file(self, code: str, language: str) -> tuple[str, str, str | None]:
        """임시 코드 파일 작성 후 (path, base_name, main_class) 반환."""
        config = self.language_configs[language]
        with tempfile.NamedTemporaryFile(suffix=config["file_ext"], mode="w", delete=False) as f:
            if language == "java":
                main_class = config["main_class"]
                code = f"public class {main_class} {{\n{code}\n}}"
            f.write(code)
            base = os.path.splitext(f.name)[0]
            return f.name, base, (config["main_class"] if language == "java" else None)

    def _compile_code(self, file_path: str, language: str, base_name: str) -> tuple[bool, str, int]:
        """
        필요 언어면 컴파일 수행.
        반환: (성공여부, 에러문자열, peak_rss_bytes)
        """
        config = self.language_configs[language]
        if not config["compile_cmd"]:
            return True, "", 0

        try:
            cmd = [c.format(file=file_path, exe=base_name, class_name=config.get("main_class", "")) for c in config["compile_cmd"]]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            proc = psutil.Process(process.pid)

            # ★ sampler 스레드 시작
            peak, stop, t = _sample_peak_rss(proc)

            try:
                _, stderr = process.communicate(timeout=self.TIMEOUT)
            finally:
                # ★ sampler 종료/정리
                stop.set()
                t.join()

            err = (stderr.decode(errors="replace") if stderr else "")
            return (process.returncode == 0), err, peak
        except subprocess.TimeoutExpired:
            return False, "Compilation timed out", 0
        except Exception as e:
            return False, str(e), 0

    # --------------------------
    # 판정
    # --------------------------
    def _judge(self, output: str, expected: str, rating_mode: RatingMode) -> bool:
        """
        problem_Normalization.compare 를 최대한 활용.
        Enum/문자열 혼용 이슈는 계단식 폴백으로 처리.
        """
        try:
            return bool(problem_Normalization.compare(output, expected, rating_mode))
        except TypeError:
            pass
        except Exception:
            pass

        try:
            mode_val = str(getattr(rating_mode, "value", rating_mode))
            return bool(problem_Normalization.compare(output, expected, mode_val))
        except Exception:
            pass

        out = (output or "").strip()
        exp = (expected or "").strip()
        mv = str(getattr(rating_mode, "value", rating_mode)).lower()

        if "regex" in mv:
            import re
            try:
                return re.fullmatch(exp, out) is not None
            except re.error:
                return False
        if "space" in mv or "whitespace" in mv:
            return "".join(out.split()) == "".join(exp.split())
        return out == exp

    # --------------------------
    # 단일 테스트 실행
    # --------------------------
    def _run_test_case(
        self,
        file_path: str,
        language: str,
        base_name: str,
        test_case: TestCaseInput,
        test_case_index: int,
        rating_mode: RatingMode,
    ) -> RunnerTestResult:
        config = self.language_configs[language]
        cmd = [c.format(file=file_path, exe=base_name, class_name=config.get("main_class", "")) for c in config["run_cmd"]]

        start = time.time()
        try:
            process = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            proc = psutil.Process(process.pid)

            # ✅ 샘플러 시작 → 즉시 communicate 로 stdin 전달
            stop, t, peak = _sample_peak_rss(proc)
            try:
                stdout, stderr = process.communicate(input=test_case.input, timeout=self.TIMEOUT)
            finally:
                stop.set()
                t.join()

            exec_ms = (time.time() - start) * 1000.0
            output = (stdout or "").strip()
            passed = self._judge(output, test_case.expected_output, rating_mode)

            return RunnerTestResult(
                test_case_index=test_case_index,
                status="SUCCESS",
                output=output,
                error=(stderr if stderr else None),
                execution_time=exec_ms,
                memory_usage=int(peak[0] or 0),
                passed=passed,
                input=test_case.input,
                expected_output=test_case.expected_output,
            )
        except subprocess.TimeoutExpired:
            return RunnerTestResult(
                test_case_index=test_case_index,
                status="TIMEOUT",
                output="",
                error="Execution timed out",
                execution_time=self.TIMEOUT * 1000.0,
                memory_usage=0,
                passed=False,
                input=test_case.input,
                expected_output=test_case.expected_output,
            )
        except Exception as e:
            return RunnerTestResult(
                test_case_index=test_case_index,
                status="ERROR",
                output="",
                error=str(e),
                execution_time=0.0,
                memory_usage=0,
                passed=False,
                input=test_case.input,
                expected_output=test_case.expected_output,
            )

    def _check_runtime(self, language: str) -> tuple[bool, str]:
        """
        필요한 실행 파일이 없는 경우 미리 감지하여 친절한 에러 메시지 제공.
        """
        cfg = self.language_configs[language]
        # run_cmd / compile_cmd 에 포함된 실행 파일들을 which 로 점검
        bins = []
        if cfg.get("run_cmd"):
            bins.append(str(cfg["run_cmd"][0]))
        if cfg.get("compile_cmd"):
            bins.append(str(cfg["compile_cmd"][0]))
        for b in bins:
            # 경로 템플릿일 수도 있으니 변수 치환 제거
            b = b.split()[0].strip()
            if "{" in b:  # 템플릿이면 스킵
                continue
            if shutil.which(b) is None:
                return False, f"Required runtime '{b}' is not installed on server."
        return True, ""
    # --------------------------
    # 메인 실행
    # --------------------------
    def run_code(
        self,
        code: str,
        language: str,
        test_cases: List[TestCaseInput],
        rating_mode: RatingMode,
    ) -> Dict[str, Any]:
        file_path = ""
        base_name = ""
        compile_peak = 0
        try:
            # ★ 런타임 사전 점검
            ok, msg = self._check_runtime(language)
            if not ok:
                # 케이스마다 동일 에러 리턴하여 프론트에 친절히 노출
                return {
                    "success": False,
                    "results": [
                        {
                            "test_case_index": i,
                            "status": _ES("ERROR"),
                            "output": "",
                            "error": msg,
                            "execution_time": 0.0,
                            "memory_usage": 0,
                            "passed": False,
                            # ⬇ input/expected 그대로 담아줌
                            "input": tc.input,
                            "expected_output": tc.expected_output,
                        }
                        for i, tc in enumerate(test_cases)
                    ],
                    "overall_status": _OS("FAILED"),
                }

            # ===== 이하 기존 흐름 유지 =====
            file_path, base_name, _ = self._prepare_code_file(code, language)

            if self.language_configs[language]["compile_cmd"]:
                success, error, compile_peak = self._compile_code(file_path, language, base_name)
                if not success:
                    return {
                        "success": False,
                        "results": [{
                            "test_case_index": 0,
                            "status": _ES("ERROR"),
                            "output": "",
                            "error": f"Compilation error: {error}",
                            "execution_time": 0.0,
                            "memory_usage": compile_peak,
                            "passed": False,
                            "input": "", "expected_output": "",
                        }],
                        "overall_status": _OS("FAILED"),
                        "compile_memory_usage": compile_peak,
                    }

            results: List[TestCase] = []
            for i, tc in enumerate(test_cases):
                r = self._run_test_case(
                    file_path=file_path,
                    language=language,
                    base_name=base_name,
                    test_case=tc,
                    test_case_index=i,
                    rating_mode=rating_mode,
                )
                results.append(r)

            passed_count = sum(1 for r in results if r.passed)
            if passed_count == len(test_cases):
                overall_status = _OS("SUCCESS")
            elif passed_count == 0:
                overall_status = _OS("FAILED")
            else:
                overall_status = _OS("PARTIAL")

            return {
                "success": True,
                "results": results,
                "overall_status": overall_status,
                "compile_memory_usage": compile_peak,
            }

        finally:
            # 임시파일 정리 (기존 그대로)
            try:
                if file_path and os.path.exists(file_path):
                    os.unlink(file_path)
                if language in ["c", "cpp"]:
                    try:
                        if os.path.exists(base_name):
                            os.unlink(base_name)
                    except FileNotFoundError:
                        pass
                elif language == "java":
                    try:
                        class_file = f"{base_name}.class"
                        if os.path.exists(class_file):
                            os.unlink(class_file)
                    except FileNotFoundError:
                        pass
            except Exception:
                pass