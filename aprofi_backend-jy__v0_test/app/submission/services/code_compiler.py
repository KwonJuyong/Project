import subprocess, tempfile, os, time, psutil, re, sys
from enum import Enum
from typing import List, Dict, Any, Tuple

# ★ DB Enum 이름과 값이 같다면 아래 import 사용.
#   다르면 DB Enum을 임포트해 매핑하세요.
from app.submission.services.problem_Normalization import RatingMode as _RatingMode, problem_Normalization

RatingMode = _RatingMode  # 혼동 방지

class ExecutionStatusEnum(str, Enum):
    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"

class OverallStatus(str, Enum):
    ALL_PASSED = "ALL_PASSED"
    SOME_FAILED = "SOME_FAILED"
    ALL_FAILED = "ALL_FAILED"

class RatingMode(str, Enum):
    HARD = "hard"
    SPACE = "space"
    REGEX = "regex"
    NONE = "none"

class CodeRunner:
    TIMEOUT = 5  # seconds
    MEMORY_LIMIT = 512 * 1024 * 1024  # 512MB
    FILE_SIZE_LIMIT = 64 * 1024 * 1024  # 64MB

    def __init__(self):
        self.language_configs = {
            "python": {"ext": ".py", "compile": None, "run": ["python", "{file}"]},
            "java":   {"ext": ".java", "compile": ["javac", "{file}"], "run": ["java", "{class_name}"], "main_class": "Solution"},
            "cpp":    {"ext": ".cpp", "compile": ["g++", "-O2", "-o", "{exe}", "{file}"], "run": ["./{exe}"]},
            "c":      {"ext": ".c",   "compile": ["gcc", "-O2", "-o", "{exe}", "{file}"], "run": ["./{exe}"]},
            "javascript": {"ext": ".js", "compile": None, "run": ["node", "{file}"]},
        }

    # ---------- helpers ----------
    def _apply_limits_preexec(self):
        """리눅스 한정: 프로세스 자원 제한"""
        if sys.platform.startswith("linux"):
            try:
                import resource
                # CPU 시간(초)
                resource.setrlimit(resource.RLIMIT_CPU, (self.TIMEOUT + 1, self.TIMEOUT + 1))
                # 최대 가상메모리(bytes)
                resource.setrlimit(resource.RLIMIT_AS, (self.MEMORY_LIMIT, self.MEMORY_LIMIT))
                # 파일 사이즈 제한
                resource.setrlimit(resource.RLIMIT_FSIZE, (self.FILE_SIZE_LIMIT, self.FILE_SIZE_LIMIT))
                # 프로세스 개수 제한(간단 안전장치)
                resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
            except Exception:
                pass  # 컨테이너 권한 등에 따라 실패할 수 있음

    def _prepare_code_file(self, dirpath: str, code: str, language: str) -> Tuple[str, str, str | None]:
        config = self.language_configs[language]
        file_path = os.path.join(dirpath, f"Main{config['ext']}")
        if language == "java":
            main_class = config["main_class"]
            # 클래스 중복 선언 방지
            if not re.search(r"\bclass\s+\w+\b", code):
                code = f"public class {main_class} {{\n{code}\n}}\n"
        else:
            main_class = None
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)
        base_name, _ = os.path.splitext(file_path)
        return file_path, base_name, main_class

    def _compile(self, cwd: str, file_path: str, language: str, base_name: str, main_class: str | None) -> Tuple[bool, str]:
        config = self.language_configs[language]
        if not config["compile"]:
            return True, ""
        cmd = [c.format(file=file_path, exe=base_name, class_name=main_class or "") for c in config["compile"]]
        try:
            proc = subprocess.Popen(
                cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                preexec_fn=self._apply_limits_preexec if sys.platform.startswith("linux") else None
            )
            _, stderr = proc.communicate(timeout=self.TIMEOUT)
            return proc.returncode == 0, (stderr or "")
        except subprocess.TimeoutExpired:
            return False, "Compilation timed out"
        except Exception as e:
            return False, str(e)

    def _run_case(self, cwd: str, language: str, file_path: str, base_name: str,
                  main_class: str | None, tc: Dict[str, str], idx: int, rating_mode: RatingMode) -> Dict[str, Any]:
        config = self.language_configs[language]
        cmd = [c.format(file=file_path, exe=base_name, class_name=main_class or "") for c in config["run"]]
        start = time.time()
        try:
            proc = subprocess.Popen(
                cmd, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                preexec_fn=self._apply_limits_preexec if sys.platform.startswith("linux") else None
            )
            ps = psutil.Process(proc.pid)
            stdout, stderr = proc.communicate(input=tc.get("input", ""), timeout=self.TIMEOUT)
            try:
                rss = ps.memory_info().rss
            except Exception:
                rss = 0
            elapsed_ms = (time.time() - start) * 1000.0
            output = (stdout or "").strip()

            expected = (tc.get("expected_output") or "").strip()
            passed = problem_Normalization.compare(output, expected, rating_mode)

            return {
                "test_case_index": idx,
                "status": ExecutionStatusEnum.SUCCESS.value,
                "output": output,
                "error": (stderr or None),
                "execution_time": elapsed_ms,
                "memory_usage": rss,
                "passed": bool(passed),
            }
        except subprocess.TimeoutExpired:
            return {"test_case_index": idx, "status": ExecutionStatusEnum.TIMEOUT.value, "output": "", "error": "Execution timed out", "execution_time": self.TIMEOUT * 1000, "memory_usage": 0, "passed": False}
        except Exception as e:
            return {"test_case_index": idx, "status": ExecutionStatusEnum.ERROR.value, "output": "", "error": str(e), "execution_time": 0, "memory_usage": 0, "passed": False}

    # ---------- public ----------
    def run_code(self, code: str, language: str, test_cases: List[Dict[str, str]], rating_mode: RatingMode) -> Dict[str, Any]:
        language = language.lower()
        if language not in self.language_configs:
            return {"success": False, "results": [{"test_case_index": 0, "status": ExecutionStatusEnum.ERROR.value, "output": "", "error": f"Unsupported language: {language}", "execution_time": 0, "memory_usage": 0, "passed": False}], "overall_status": OverallStatus.ALL_FAILED.value}

        with tempfile.TemporaryDirectory(prefix="runner_") as tmpdir:
            file_path, base_name, main_class = self._prepare_code_file(tmpdir, code, language)

            ok, err = self._compile(tmpdir, file_path, language, base_name, main_class)
            if not ok:
                return {"success": False, "results": [{"test_case_index": 0, "status": ExecutionStatusEnum.ERROR.value, "output": "", "error": f"Compilation error: {err}", "execution_time": 0, "memory_usage": 0, "passed": False}], "overall_status": OverallStatus.ALL_FAILED.value}

            results = [self._run_case(tmpdir, language, file_path, base_name, main_class, tc, i, rating_mode)
                       for i, tc in enumerate(test_cases)]

        passed_count = sum(1 for r in results if r.get("passed"))
        if passed_count == len(results) and len(results) > 0:
            overall = OverallStatus.ALL_PASSED.value
        elif passed_count == 0:
            overall = OverallStatus.ALL_FAILED.value
        else:
            overall = OverallStatus.SOME_FAILED.value

        return {"success": True, "results": results, "overall_status": overall}