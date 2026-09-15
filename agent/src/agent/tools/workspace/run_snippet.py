"""run_snippet tool: in-harness lightweight code snippet execution for teaching and demonstrations.

Executes a short code snippet (Python via host executable, JS/TS via Node.js
with type stripping) with cwd pinned to the sandbox directory under the
workspace, bounds execution time, captures stdout/stderr, enhances exceptions
with pedagogical guidance, and reports any generated images/charts.

Responsibilities:
- Support multi-language script execution (Python via host executable, JS/TS via Node.js).
- Enforce strict timeouts and resource limits (default 5s, capped at 15s).
- Run with cwd pinned to `workspace/sandbox/snippets` (not a chroot: absolute
  paths, `..`, and interpreters on PATH can still escape that directory,
  same limitation as run_shell).
- Provide pedagogical error extraction for novice guidance.
- Detect and report newly generated visualization artifacts (.png, .svg, .jpg).
"""

from __future__ import annotations

import asyncio
import re
import sys
import uuid
from contextlib import suppress
from pathlib import Path

from agent.tools.core.base import AgentTool

_MAX_COLLECT_BYTES = 100_000
_MAX_CODE_CHARS = 100_000
_MAX_TIMEOUT_SECONDS = 15
_DEFAULT_TIMEOUT_SECONDS = 5

_DESTRUCTIVE_PATTERNS = re.compile(
    r"\bmkfs\b|\brm\s+-rf\s+[/~]|\bformat\s+[a-z]:|\bdiskpart\b|\bdel\s+/[sS]\s+/[qQ]\s+[cC]:"
    r"|rmSync\s*\(\s*['\"`]/|rmdir\s+/[sS]\s+/[qQ]|shutil\.rmtree\s*\(\s*['\"`]/",
    re.IGNORECASE,
)


def _extract_pedagogical_error(stderr_text: str, language: str = "python") -> str:
    """Extract standard runtime error names and generate concise pedagogical hints."""
    lines = [line.strip() for line in stderr_text.strip().splitlines() if line.strip()]
    if not lines:
        return ""
    combined = "\n".join(lines)

    if language in ("javascript", "typescript", "js", "ts", "node"):
        if "TypeError:" in combined or "TypeError" in combined:
            return "\n[教学诊断] 检测到类型错误 (TypeError): 尝试访问未定义 (undefined/null) 的属性，或调用了非函数对象。"
        if "ReferenceError:" in combined or "ReferenceError" in combined:
            return "\n[教学诊断] 检测到引用错误 (ReferenceError): 使用了未声明或在当前作用域不可达的变量名。"
        if "SyntaxError:" in combined or "SyntaxError" in combined:
            return "\n[教学诊断] 检测到语法错误 (SyntaxError): 代码结构不符合 JS/TS 规范（如括号未闭合或非法符号）。"
        if "RangeError:" in combined or "RangeError" in combined:
            return "\n[教学诊断] 检测到范围错误 (RangeError): 常见于无限递归导致栈溢出，或数组长度超限。"
        last_line = lines[-1]
        return f"\n[教学诊断] 执行抛出异常: {last_line}"

    last_line = lines[-1]
    if "ZeroDivisionError" in last_line:
        return "\n[教学诊断] 检测到除零错误 (ZeroDivisionError): 数学上除数不能为 0，请检查分母表达式。"
    if "IndexError" in last_line:
        return "\n[教学诊断] 检测到索引越界 (IndexError): 访问了超出序列长度的索引，请检查循环范围或列表边界。"
    if "KeyError" in last_line:
        return "\n[教学诊断] 检测到字典键不存在 (KeyError): 尝试访问未初始化的字典键，可考虑使用 dict.get(key, default)。"
    if "TypeError" in last_line:
        return "\n[教学诊断] 检测到类型不匹配 (TypeError): 运算或函数传参的类型不符合预期，请检查变量类型或进行显式转换。"
    if "NameError" in last_line:
        return "\n[教学诊断] 检测到变量未定义 (NameError): 使用了未赋值的变量名或拼写错误，请检查变量作用域与声明。"
    if "SyntaxError" in last_line:
        return "\n[教学诊断] 检测到语法错误 (SyntaxError): 代码结构不符合 Python 语法规则（如缺少冒号、括号不匹配或缩进问题）。"
    return f"\n[教学诊断] 执行抛出异常: {last_line}"


def run_snippet_tool(workspace: str | Path) -> AgentTool:
    ws = Path(workspace)
    sandbox_dir = ws / "sandbox" / "snippets"

    async def run_snippet(
        code: str,
        language: str = "python",
        timeout: int = _DEFAULT_TIMEOUT_SECONDS,
    ) -> str:
        if not code or not code.strip():
            return "[执行跳过] 代码片段为空"

        if len(code) > _MAX_CODE_CHARS:
            return f"[参数错误] 代码片段长度超过 {_MAX_CODE_CHARS} 字符限制。"

        if _DESTRUCTIVE_PATTERNS.search(code):
            return "[安全拒绝] 代码包含高危系统级破坏性命令，已被安全策略拦截。"

        lang = (language or "python").lower().strip()
        if lang in ("python", "py"):
            ext = ".py"
            cmd = [sys.executable, "-u"]
            norm_lang = "python"
        elif lang in ("javascript", "js", "node"):
            ext = ".mjs"
            cmd = ["node"]
            norm_lang = "javascript"
        elif lang in ("typescript", "ts"):
            ext = ".ts"
            cmd = ["node"]
            norm_lang = "typescript"
        else:
            return (
                f"[暂不支持] 当前支持 python / javascript / typescript 代码演示，收到: {language}"
            )

        try:
            raw_timeout = int(timeout) if timeout is not None else _DEFAULT_TIMEOUT_SECONDS
        except (ValueError, TypeError):
            raw_timeout = _DEFAULT_TIMEOUT_SECONDS
        timeout_sec = min(max(1, raw_timeout), _MAX_TIMEOUT_SECONDS)

        sandbox_dir.mkdir(parents=True, exist_ok=True)
        snip_id = uuid.uuid4().hex[:8]
        script_path = sandbox_dir / f"snip_{snip_id}{ext}"

        try:
            existing_files = set(sandbox_dir.iterdir())
        except OSError:
            existing_files = set()

        try:
            script_path.write_text(code, encoding="utf-8")
        except OSError as exc:
            return f"[写入失败] 无法创建临时代码文件: {exc}"

        exec_cmd = [*cmd, str(script_path)]

        try:
            proc = await asyncio.create_subprocess_exec(
                *exec_cmd,
                cwd=str(sandbox_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            with suppress(OSError):
                script_path.unlink(missing_ok=True)
            runtime_name = "Python" if norm_lang == "python" else "Node.js (node)"
            return f"[环境缺失] 未在系统中检测到执行所需的环境: {runtime_name}。"
        except OSError as exc:
            with suppress(OSError):
                script_path.unlink(missing_ok=True)
            return f"[启动失败] 操作系统无法启动子进程: {exc}"
        except Exception as exc:  # noqa: BLE001
            with suppress(OSError):
                script_path.unlink(missing_ok=True)
            return f"[启动失败] 子进程启动异常: {exc}"

        timed_out = False
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_sec
            )
        except TimeoutError:
            timed_out = True
            with suppress(ProcessLookupError, OSError):
                proc.kill()
            with suppress(Exception):
                await proc.wait()
            stdout_bytes, stderr_bytes = b"", b""
        finally:
            with suppress(OSError):
                script_path.unlink(missing_ok=True)

        if timed_out:
            return f"[超时] 代码执行超过 {timeout_sec} 秒上限，已终止。教学演示建议优化算法复杂度或减少计算量。"

        stdout_text = stdout_bytes[:_MAX_COLLECT_BYTES].decode("utf-8", errors="replace").strip()
        stderr_text = stderr_bytes[:_MAX_COLLECT_BYTES].decode("utf-8", errors="replace").strip()

        try:
            new_files = set(sandbox_dir.iterdir()) - existing_files
        except OSError:
            new_files = set()
        image_artifacts = [
            f.name for f in new_files if f.suffix.lower() in (".png", ".svg", ".jpg", ".jpeg")
        ]
        artifacts_hint = ""
        if image_artifacts:
            artifacts_hint = "\n[生成图表] " + ", ".join(
                f"sandbox/snippets/{name}" for name in image_artifacts
            )

        if proc.returncode == 0:
            output = stdout_text or "(代码成功执行，无标准输出)"
            return f"exit=0\n{output}{artifacts_hint}"

        error_body = stderr_text or stdout_text or "未知执行错误"
        pedagogy = _extract_pedagogical_error(stderr_text, language=norm_lang)
        return f"exit={proc.returncode}\n{error_body}{pedagogy}{artifacts_hint}"

    return AgentTool(
        name="run_snippet",
        description=(
            "在沙箱执行轻量代码片段进行概念教学或计算演示(支持 Python / JavaScript / TypeScript;"
            "超时上限 15s;自动捕获标准输出、异常诊断及生成图表)"
        ),
        handler=run_snippet,
        dimension="workspace",
        write=True,
        schema={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "要运行的代码内容"},
                "language": {
                    "type": "string",
                    "description": "编程语言，支持 python / javascript / typescript (默认 python)",
                },
                "timeout": {"type": "integer", "description": "执行超时秒数，默认 5，最大 15"},
            },
            "required": ["code"],
        },
    )


__all__ = ["run_snippet_tool"]
