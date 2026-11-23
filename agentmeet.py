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
        "在单个 Agent 命令后加 -w 或 --write 可读写项目，可在参数后直接输入指示。\n"
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


def ask(agent, history, workspace, model, writable=False):
    executable = shutil.which(agent)
    if not executable and agent == "agy" and os.name == "nt":
        installed = Path.home() / "AppData/Local/agy/bin/agy.exe"
        if installed.is_file():
            executable = str(installed)
    if not executable:
        raise OSError(f"找不到 {agent}。请先安装 CLI 并加入 PATH。")
    action = ("本轮可读写当前项目。按用户指示实际创建或修改文件，并说明改动的相对路径。"
              if writable else "本轮只读分析，保持项目文件原样。")
    prompt = (
        f"你是讨论中的 {NAMES[agent]}。请根据以下完整发言记录参与讨论，用用户的语言回答。"
        "当前目录是本次讨论的项目。按需检索和阅读其中的文件，引用相关相对路径。"
        f"{action}记录按时间排序。\n" + history
    )
    with tempfile.TemporaryDirectory(prefix="roundtable-") as directory:
        final_file = Path(directory, "reply.txt")
        if agent == "codex":
            args = ["-a", "never", "exec", "--skip-git-repo-check", "--ephemeral",
                    "--ignore-user-config", "--ignore-rules", "--disable", "plugins",
                    "--disable", "apps", "--disable", "hooks", "--sandbox",
                    "workspace-write" if writable else "read-only", "--output-last-message", str(final_file), "-"]
        elif agent == "claude":
            tools = "Read,Glob,Grep,Edit,Write" if writable else "Read,Glob,Grep"
            args = ["-p", "--output-format", "text", "--no-session-persistence",
                    "--restricted", "--strict-mcp-config", "--disable-slash-commands",
                    "--permission-mode", "acceptEdits" if writable else "dontAsk", "--tools", tools,
                    "--allowedTools", tools]
        else:
            settings = {"allowNonWorkspaceAccess": False, "toolPermission": "request-review",
                        "permissions": {"deny": ["command(*)", "mcp(*)",
                                                 "execute_url(*)", "read_url(*)"]}}
            if not writable:
                settings["permissions"]["deny"].append("write_file(*)")
            policy = Path(directory, "settings.json")
            policy.write_text(json.dumps(settings), encoding="utf-8")
            args = ["--settings", str(policy), "--disable-slash-commands",
                    "--mode", "accept-edits" if writable else "plan", "--input-format", "stream-json",
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


def turn(agent, snapshot, workspace, model, writable=False):
    try:
        return agent, ask(agent, snapshot, workspace, model, writable), None
    except subprocess.TimeoutExpired:
        return agent, None, "等待超过 10 分钟。"
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        return agent, None, str(error)


def main():
    parser = argparse.ArgumentParser(prog="agentmeet", description="在当前项目目录启动多 Agent 讨论")
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
    print(f"AgentMeet · 多 Agent 讨论室\n项目目录：{workspace}\n" + HELP)
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
        writable = command in COMMANDS and len(parts) >= 2 and parts[1] in {"-w", "--write"}
        if writable and len(parts) == 3:
            history.append({"speaker": "用户", "text": parts[2]})
        if len(parts) > 1 and not writable:
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
        mode = "（可读写）" if writable else "（只读）"
        print(mode + "等待 " + "、".join(NAMES[a] for a in agents) + " 发言…", flush=True)
        with ThreadPoolExecutor(max_workers=len(agents)) as pool:
            tasks = [pool.submit(turn, agent, snapshot, workspace, models[agent], writable)
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

