"""由用户点名的多 Agent 讨论终端。使用 Python 3.9+ 运行。"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import subprocess
import json
from pathlib import Path
import shutil
import sys
import tempfile


NAMES = {"codex": "GPT", "claude": "Claude", "agy": "Gemini"}
COMMANDS = {name.lower(): agent for agent, name in NAMES.items()}
COMMANDS.update({"codex": "codex", "code": "codex", "agy": "agy"})
HELP = ("输入消息后按回车，再用 /gpt、/claude、/gemini 或 /all 点名。\n"
        "/report <agent> [文件.md] 将讨论整理成报告。\n"
        "/model 查看模型；/model <agent> <模型名> 设置；用 default 恢复默认。/exit 退出。")


def agy_reply(output):
    for line in output.splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("event") == "result":
            result = event["result"]
            if result.get("is_error") or result.get("status") == "ERROR":
                raise ValueError(result.get("response") or str(result))
            return result.get("response", "")
    raise ValueError("agy 没有返回 result 事件，请检查 CLI 版本。")


def ask(agent, history, workspace, model):
    executable = shutil.which(agent)
    if not executable and agent == "agy" and os.name == "nt":
        installed = Path.home() / "AppData/Local/agy/bin/agy.exe"
        if installed.is_file():
            executable = str(installed)
    if not executable:
        raise OSError(f"找不到 {agent}。请先安装 CLI 并加入 PATH。")
    prompt = (
        f"你是讨论中的 {NAMES[agent]}。请根据以下完整发言记录参与讨论，用用户的语言回答。"
        "当前目录是本次讨论的项目。按需检索和阅读其中的文件，引用相关相对路径。"
        "只读分析，保持项目文件原样。只发表本人的观点。记录按时间排序。\n" + history
    )
    with tempfile.TemporaryDirectory(prefix="roundtable-") as directory:
        final_file = Path(directory, "reply.txt")
        if agent == "codex":
            args = ["-a", "never", "exec", "--skip-git-repo-check", "--ephemeral",
                    "--ignore-user-config", "--ignore-rules", "--disable", "plugins",
                    "--disable", "apps", "--disable", "hooks", "--sandbox",
                    "read-only", "--output-last-message", str(final_file), "-"]
        elif agent == "claude":
            args = ["-p", "--output-format", "text", "--no-session-persistence",
                    "--restricted", "--strict-mcp-config", "--disable-slash-commands",
                    "--permission-mode", "dontAsk", "--tools", "Read,Glob,Grep",
                    "--allowedTools", "Read,Glob,Grep"]
        else:
            settings = {"allowNonWorkspaceAccess": False, "toolPermission": "request-review",
                        "permissions": {"deny": ["write_file(*)", "command(*)", "mcp(*)",
                                                 "execute_url(*)", "read_url(*)"]}}
            policy = Path(directory, "settings.json")
            policy.write_text(json.dumps(settings), encoding="utf-8")
            args = ["--settings", str(policy), "--disable-slash-commands",
                    "--mode", "plan", "--input-format", "stream-json",
                    "--output-format", "stream-json"]
            prompt = json.dumps({"event": "user", "message": {"content": prompt}})
        if model:
            if Path(executable).suffix.lower() in {".cmd", ".bat"} and any(
                    char in model for char in '"&|<>^%!\r\n'):
                raise ValueError("此模型名含有 Windows 批处理启动器不支持的字符。")
            args.insert(3 if agent == "codex" else 0, "--model=" + model)
        process = subprocess.run(
            [executable, *args], cwd=workspace, input=(prompt + "\n").encode("utf-8"),
            capture_output=True, timeout=600,
        )
        output = process.stdout.decode("utf-8", errors="replace")
        if process.returncode:
            detail = process.stderr.decode("utf-8", errors="replace").strip() or output.strip()
            raise ValueError(detail[-1500:] or f"退出码 {process.returncode}")
        if agent == "codex":
            output = final_file.read_text(encoding="utf-8")
        elif agent == "agy":
            output = agy_reply(output)
        if not isinstance(output, str) or not output.strip():
            raise ValueError("CLI 返回了空回答。")
        return output.strip()


def turn(agent, snapshot, workspace, model):
    try:
        return agent, ask(agent, snapshot, workspace, model), None
    except subprocess.TimeoutExpired:
        return agent, None, "等待超过 10 分钟。"
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        return agent, None, str(error)


def write_report(parts, history, workspace, models):
    agent = COMMANDS.get(parts[1].lower()) if len(parts) >= 2 else None
    if agent is None:
        print("用法：/report <gpt|claude|gemini> [相对路径.md]")
        return
    if not history:
        print("请先输入讨论内容。")
        return
    relative = Path(parts[2] if len(parts) == 3 else "report.md")
    if (relative.anchor or relative.suffix.lower() != ".md"
            or any(p in {"..", ".git"} or ":" in p or Path(p).is_reserved()
                   for p in map(str.lower, relative.parts))):
        print("请指定项目目录内的相对 Markdown 路径，例如 reports/讨论总结.md。")
        return
    target = workspace / relative
    try:
        if not target.resolve().is_relative_to(workspace) or target.is_symlink():
            print("报告路径必须位于项目目录内。")
            return
        if target.exists():
            print(f"文件已存在，请换一个文件名：{relative}")
            return
        instruction = {"speaker": "用户", "text": (
            "请根据以上讨论及我的要求撰写可独立阅读的 Markdown 报告。"
            "区分已达成的结论、仍有分歧的问题以及建议。仅输出报告正文，程序负责保存。")}
        print(f"等待 {NAMES[agent]} 撰写报告…", flush=True)
        snapshot = json.dumps([*history, instruction], ensure_ascii=False)
        _, reply, error = turn(agent, snapshot, workspace, models[agent])
        if error is not None:
            print(f"[{NAMES[agent]} 调用失败] {error}")
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as draft:
            temp_path = Path(draft.name)
        try:
            temp_path.write_text(reply + "\n", encoding="utf-8")
            if os.name == "nt":
                os.rename(temp_path, target)  # Windows refuses to replace an existing file.
            else:
                os.link(temp_path, target)
        finally:
            temp_path.unlink(missing_ok=True)
    except FileExistsError:
        print(f"文件已存在，请换一个文件名：{relative}")
        return
    except (OSError, RuntimeError, ValueError) as error:
        print(f"报告保存失败：{error}")
        return
    history.extend([{"speaker": "用户", "text": f"请将讨论整理为报告 {relative}。"},
                    {"speaker": NAMES[agent], "text": reply}])
    print(f"[{NAMES[agent]}] 已保存报告：{target}")


def main():
    parser = argparse.ArgumentParser(prog="agentmeet", description="在当前项目目录启动只读讨论")
    for agent, name in NAMES.items():
        flags = [f"--{name.lower()}-model"]
        if agent != name.lower():
            flags.append(f"--{agent}-model")
        parser.add_argument(*flags, dest=f"{agent}_model", metavar="MODEL", help=f"{name} 模型名")
    options = parser.parse_args()
    models = {a: getattr(options, f"{a}_model") for a in NAMES}
    workspace = Path.cwd()
    history = []
    interactive = sys.stdin.isatty()
    print(f"AgentMeet · 多 Agent 讨论室\n只读项目目录：{workspace}\n" + HELP)
    while True:
        try:
            line = input("[用户] > " if interactive else "").strip()
        except EOFError:
            return
        if not line:
            continue
        if not line.startswith("/"):
            history.append({"speaker": "用户", "text": line})
            if not interactive:
                print("[用户] " + line)
            continue
        parts = line[1:].split(maxsplit=2)
        command = parts[0].lower() if parts else ""
        if command == "report":
            write_report(parts, history, workspace, models)
            continue
        if command == "model":
            if len(parts) == 1:
                for agent, name in NAMES.items():
                    print(f"{name}  {models[agent] or '默认'}")
            elif len(parts) == 3 and parts[1].lower() in COMMANDS:
                agent = COMMANDS[parts[1].lower()]
                models[agent] = None if parts[2].lower() == "default" else parts[2]
                print(f"{NAMES[agent]}  {models[agent] or '默认'}")
            else:
                print("用法：/model <gpt|claude|gemini> <模型名或 default>")
            continue
        if len(parts) > 1:
            print(HELP)
            continue
        if command == "exit":
            return
        if command not in COMMANDS and command != "all":
            print(HELP)
            continue
        if not history:
            print("请先输入讨论内容。")
            continue
        agents = list(NAMES) if command == "all" else [COMMANDS[command]]
        snapshot = json.dumps(history, ensure_ascii=False)
        print("等待 " + "、".join(NAMES[a] for a in agents) + " 发言…", flush=True)
        with ThreadPoolExecutor(max_workers=len(agents)) as pool:
            tasks = [pool.submit(turn, agent, snapshot, workspace, models[agent])
                     for agent in agents]
            for completed in as_completed(tasks):
                agent, reply, error = completed.result()
                if error is not None:
                    print(f"\n[{NAMES[agent]} 调用失败] {error}\n", flush=True)
                    continue
                history.append({"speaker": NAMES[agent], "text": reply})
                print(f"\n[{NAMES[agent]}]\n{reply}\n", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass

