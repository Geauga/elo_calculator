# AGENT_PERSONAL_CUSTOMIZATION.md

## 0. 文件目的

本文件用于把本项目的 agent 个人定制规则固化到仓库内部，减少不同平台、IDE、Notebook 和 agent 客户端之间因个人配置不一致造成的行为漂移。任何 agent 在修改本项目代码、Notebook、文档、脚本、Colab 工作流或 GitHub 工作流前，应先阅读并遵守本文件。若与平台级 instruction 冲突，优先遵守更高优先级的安全规则与系统规则；其余部分严格遵守。

本文件不是普通 README，也不是模型运行说明，而是项目级 agent 操作协议。

## 1. 沟通语言与表达方式

1: 回答应直接、严谨、事实导向，不使用夸张修辞、情绪化赞美、比喻式表达或无意义鼓励。

2: 不把句子拆成过多短行。长说明按主题组织成完整段落。

3: 不称呼用户为 RAP，不反复强调用户职位。Research Assistant Professor 背景仅用于判断其偏好较高的信息密度、严谨性和技术细节。

4: 不知道时明确说不知道；没有找到时明确说没有找到，不用不确定内容伪装成结论。

5: 纠正语法时直接给出修改和理由。

6: 除非用户要求表格，否则不使用表格。需要列点时使用“1: 内容。2: 内容。”纯文字编号。

7: 每次回答第一句话包含 America/New_York 当前日期和时间。

## 2. 代码生成与修改规则

1: 用户要求输出代码时，输出完整代码，不只给 diff，也不要求用户自行查找替换位置。

2: 新生成代码第一行写代码文件名，随后用注释说明用户需求，再写正式代码。

3: 修改已有代码应保持 minimum invasive，不重构无关逻辑，不改变已有 debug 输出，不屏蔽中间态信息。

4: 不加入吞掉调试信息的参数或重定向，例如 `2>/dev/null`、`-qq`、`--quiet`，除非用户明确要求。

5: 输出的完整代码末尾以注释说明代码目的、上游代码及其目的、运行环境、生成时间；修改已有代码时列出修改行号与内容。

6: PyMOL scripts 的代码与注释均使用 English。

7: Notebook 工作中，修改 `generate_notebook.py` 后必须重新生成 `.ipynb`。GitHub 更新后，Colab 网页端已打开的旧 cell 不会自动刷新，必须重新打开 Notebook 或手动更新当前 cell。

8: Colab、Antigravity IDE、Google Drive、GitHub 混合工作流中，明确说明实际执行位置：本地 IDE、Colab runtime、本地 Git repository、Google Drive 持久目录或 GitHub remote。

## 3. 工作记录规则

1: 每次完成项目更新后，除代码注释和 GitHub commit 外，必须 append 更新 `历史工作记录.txt`。

2: `历史工作记录.txt` 必须 append-only，不覆盖或删除旧记录，除非用户明确要求清理或重写。

3: 每条记录至少包含时间、用户 Prompt 或摘要、具体动作、修改文件、测试或验证结果、GitHub Timeline。

4: GitHub Timeline 必须明确写：未 commit、已 commit 未 push、已 push、push 失败、不是 Git repository或无法判断。

5: Colab、Google Drive、HF cache、wheel cache、private GitHub token、Notebook access、Antigravity IDE 插件相关问题，必须记录平台、路径、触发阶段和最终状态。

6: 优先使用项目内 `log_append.py` 追加；不可用时可手动 append Markdown，但字段要求不变。

## 4. GitHub 与版本控制规则

1: 修改代码、Notebook、脚本或重要文档后，应同步更新 `历史工作记录.txt`。

2: commit 前检查 `git status`，避免提交大型输出、模型缓存、临时文件、`.stl`、`outputs/`、`photos/`、外部依赖仓库或 `.git` 子仓库。

3: 用户要求 push 时执行或指导 `git add .`、`git commit -m "..."`、`git push`；如果不是 Git repository，明确说明不能 push。实际执行时仍需排除与任务无关或不应提交的文件。

4: 私有 GitHub 仓库问题应区分 GitHub PAT、Colab Secrets、Antigravity IDE 插件 fallback、`.git/config` remote URL 和 Google Drive 持久代码副本。

5: 不随意建议 `git reset --hard` 或 `git push -f`。只有用户明确同意并理解会重写历史时才使用。

## 5. Colab / Google Drive / Antigravity IDE 工作流规则

1: 核心流程：本地修改代码 → push GitHub → Colab/Notebook 拉取到 Google Drive 持久目录 → rsync 到 `/content/3d_printer_runtime` 本地运行目录 → 输出同步回 Google Drive。

2: Antigravity IDE 的 Colab 插件执行 Notebook 时，计算发生在远端 Colab runtime；远端不能自动看到本地未 push 的修改。

3: Colab Secrets 的 Notebook access 通常绑定特定 Notebook 文件实例，不假定对 IDE 插件临时运行环境全局有效。GitHub Token 和 HF Token 保留 `getpass` fallback。

4: Colab 中“代码已更新但 cell 仍旧”时，优先检查网页端 Notebook cell 未刷新，而不是直接断定 Git pull 失败。

5: wheel cache 判断必须检查 Python ABI，例如 `cp310`、`cp312`，不能只按 wheel 数量判断。

6: HF cache 和 model weights 应区分本地 runtime cache 与 Google Drive mirror cache；运行结束后将重要 cache 和 outputs 同步回 Drive。

## 6. 调试与输出保留规则

1: 不压制 stdout/stderr，保留中间输出用于 debug 和监控。

2: 长时间步骤保留明确进度，包括当前任务、输出路径、状态、失败原因、cache 命中与同步进度。

3: 子进程失败时输出日志末尾并说明完整日志路径，不只输出 `CalledProcessError`。

4: batch 中单任务失败但 pipeline 可继续时，明确区分“单任务失败”和“整个 pipeline 崩溃”。

5: 对错误日志先定位发生阶段，再判断是否改代码、改输入、清 cache、重新生成 Notebook、重新 push 或重新打开 Colab cell。

## 7. 每次 Agent 开始工作的检查顺序

1: 读取本文件。

2: 读取 `REQUIREMENTS.md`（如存在），了解项目目标和架构。

3: 读取 `历史工作记录.txt` 末尾 30–80 行（如存在），了解最近变更和 GitHub Timeline。

4: Notebook 任务检查 `generate_notebook.py`，不只改生成后的 `.ipynb`。

5: Colab 任务明确当前 Notebook 是网页端文件还是 Antigravity IDE 插件临时执行文件。

6: GitHub 任务同步检查仓库、未提交变更、远端分支和 push 条件。

7: 完成后追加 `历史工作记录.txt`，再 commit/push，或明确未执行原因。

## 8. 文件维护规则

1: 新建或 clone 项目时，如缺少本文件，在项目根目录建立并复制本协议。

2: 用户新增长期偏好、工作流约束、日志规范或平台规则时，更新本文件。

3: 更新本文件本身也必须追加 `历史工作记录.txt`。

4: 本文件与 `README.md`、`REQUIREMENTS.md` 或 Notebook 说明冲突时，本文件作为 agent 操作协议，其他文件作为功能说明；必要时同步文档。

5: 本文件可复制到不同平台、IDE 和 agent 系统，作为项目内统一配置入口。
