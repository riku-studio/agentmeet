# AgentMeet

AgentMeet 是一个由你主持的多 Agent 讨论终端。输入问题后，用 `/gpt`、`/claude` 或 `/gemini` 决定下一位发言者，也可以用 `/all` 同时听取三方意见。每条回复都标明发言者。

## 安装

需要 Python 3.9 或更高版本，仅使用 Python 标准库。先安装并登录准备使用的 CLI，确认可以从终端启动它。

| 发言命令 | 本地 CLI | 兼容别名 |
| --- | --- | --- |
| `/gpt` | OpenAI Codex（`codex`） | `/codex`、`/code` |
| `/claude` | Claude Code（`claude`） | — |
| `/gemini` | Google Antigravity（`agy`） | `/agy` |

在 Windows PowerShell 中安装：

```powershell
git clone https://github.com/riku-studio/agentmeet.git
cd agentmeet
.\install.cmd
```

安装脚本将程序复制到 `%USERPROFILE%\.local\bin`。如果终端找不到 `agentmeet`，将该目录加入用户 PATH，再重新打开终端。

## 主持一次讨论

在希望 Agent 阅读的项目目录中运行 `agentmeet`。也可以直接运行 `python /path/to/agentmeet.py`。两种方式都以启动时的当前目录作为只读项目背景，Agent 可以按需查阅文件。

进入讨论室后，逐行输入：

```text
请阅读 README 和源码，说明程序如何决定下一位发言者。
/gpt
请检查 GPT 的解释有没有遗漏，并指出对应的文件。
/claude
如果要支持第四个 Agent，你会怎样修改？
/all
```

输入普通文本只会将其记入讨论。上例中，Claude 会看到 GPT 的回复和你的追问。执行 `/all` 时，三者同时收到点名前的同一份讨论记录，各自独立回答。回复按完成顺序显示，下一轮能看到本轮所有成功回复。

输入 `/exit` 退出。AgentMeet 的讨论记录只保留在本次进程的内存中。

## 将讨论写成报告

先输入对读者、篇幅或结构的要求，再点名一位 Agent 撰写。例如：

```text
给产品负责人写一份一页报告，列出结论、尚未解决的问题和下一步。
/report claude reports/方案评审.md
```

使用 `/report <gpt|claude|gemini> [相对路径.md]`。省略路径时保存到项目根目录的 `report.md`。Agent 使用当前选定的模型和完整讨论记录生成正文，由 AgentMeet 创建目录并写入 UTF-8 Markdown 文件。已有同名文件时会提示另选文件名。保存后的正文也加入讨论记录，可继续点名其他 Agent 复核。

## 选择模型

输入 `/model` 查看三位发言者的模型设置。使用 `/model <gpt|claude|gemini> <模型名>` 切换，模型名由对应 CLI 支持，设置从下一次点名起生效。例如：

```text
/model claude sonnet
/model
/model claude default
```

`default` 会清除这次会话对该 Agent 的模型指定。启动时也可以通过 `--gpt-model`、`--claude-model` 和 `--gemini-model` 分别设置，例如 `agentmeet --claude-model sonnet`。

## 许可证

本项目采用 [MIT License](LICENSE)。
