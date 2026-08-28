# 笔记本接管项目：完整迁移步骤（不迁移 DeepSeek API Key）

> 编写日期：2026-08-28  
> 适用场景：公司电脑只做最后一次导出；以后只在个人笔记本上开发。  
> GitHub 仓库：`https://github.com/zhangkai333/finance-insight-agent`  
> **最高优先级安全规则：不复制 `.env`，不迁移、不截图、不粘贴、不上传 DeepSeek API Key。**

---

## 一、先理解这次迁移分成哪三部分

| 内容 | 迁移方式 | 是否放 GitHub |
|---|---|---|
| Python 源代码、测试、脚本、项目文档 | 笔记本从 GitHub 克隆 | 是 |
| SQLite 数据库、处理结果、评估结果、日志、原始资料 | U 盘或移动硬盘私下迁移 | 否 |
| `.env` 和 DeepSeek API Key | **不迁移**；笔记本重新创建 `.env` | **绝对不可以** |
| `.venv`、缓存、临时文件 | 不迁移；笔记本重新生成 | 否 |

当前公司电脑中需要私下迁移的数据大约为：

- `data/`：约 45.62 MB，共约 295 个文件；
- `资料待放入/`：约 614.61 MB，共 540 个文件；
- 合计约 660 MB，建议移动硬盘至少预留 2 GB 空间。

本项目的安全迁移脚本会复制全部 `data/` 和原始资料，但会主动拒绝导出 `.env`。

---

# 第一部分：公司电脑最后一次操作

## 第 1 步：确认 GitHub 代码已经同步

在公司电脑项目目录打开 PowerShell：

```powershell
cd "C:\Users\admin\Documents\ChatGPT\泰迪杯B题agent应用开发项目"
git status --short --branch
git remote -v
```

当前正常结果应包含：

```text
## main...origin/main
origin  https://github.com/zhangkai333/finance-insight-agent.git
```

如果 `git status` 下面还列出了修改文件，先不要删除公司电脑上的项目。需要先判断这些修改是否应该提交到 GitHub。

> 本文档和安全迁移脚本本身是新修改；迁移前需要在 GitHub Desktop 中提交并 Push，具体见本文最后的“公司电脑现在立刻要做什么”。

---

## 第 2 步：准备移动硬盘或 U 盘

1. 插入移动硬盘或 U 盘；
2. 在“此电脑”中查看盘符，例如 `E:`；
3. 确认可用空间至少 2 GB；
4. 下文统一以 `E:` 为例。你的盘符不是 `E:` 时，必须替换成自己的盘符。

建议先在移动硬盘中新建：

```text
E:\FinanceInsightBackup
```

不要把迁移包放在项目目录内，也不要上传百度网盘、公开网盘或 GitHub。

---

## 第 3 步：导出全部本地数据和原始资料

在项目根目录执行：

```powershell
cd "C:\Users\admin\Documents\ChatGPT\泰迪杯B题agent应用开发项目"

powershell -ExecutionPolicy Bypass -File .\scripts\export_transfer_bundle.ps1 `
  -Destination "E:\FinanceInsightBackup" `
  -IncludeAllLocalData `
  -IncludeSourceDocuments
```

执行完成后，PowerShell 会显示类似：

```text
Transfer bundle created: E:\FinanceInsightBackup\finance-insight-transfer-20260828-xxxxxx
The bundle intentionally excludes .env and API keys.
Files are checksummed in manifest.sha256.json.
```

### 绝对不要做的事情

不要在命令中添加下面这个参数：

```powershell
-IncludeEnv
```

安全脚本现在即使收到这个参数也会直接报错，不会复制 `.env`。

### Docker 数据是否需要导出

目前最重要的数据已经在 `data/` 中。一般不需要迁移 Docker 容器和 Redis 缓存。

只有你明确知道自己还在 Docker MySQL 中保存了无法重新生成的数据，才在上述命令后增加：

```powershell
-IncludeDockerVolumes
```

如果不确定，不加即可。

---

## 第 4 步：确认迁移包中没有 `.env`

执行：

```powershell
$latest = Get-ChildItem -LiteralPath "E:\FinanceInsightBackup" -Directory |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1

$envFiles = Get-ChildItem -LiteralPath $latest.FullName -Recurse -Force -File |
  Where-Object { $_.Name -eq ".env" }

if ($envFiles) {
  Write-Host "停止迁移：发现 .env，请删除整个迁移包后重新导出！" -ForegroundColor Red
} else {
  Write-Host "检查通过：迁移包中没有 .env。" -ForegroundColor Green
}
```

必须看到：

```text
检查通过：迁移包中没有 .env。
```

还可以查看迁移包：

```powershell
explorer.exe $latest.FullName
```

正常情况下应该看到：

```text
data\
资料待放入\
manifest.sha256.json
README-TRANSFER.txt
```

不应该看到：

```text
.env
.venv\
.git\
```

---

## 第 5 步：安全弹出移动硬盘

1. 等待复制完全结束；
2. 关闭所有正在查看移动硬盘文件的窗口；
3. 使用 Windows 任务栏的“安全删除硬件并弹出媒体”；
4. 再拔出移动硬盘。

到这里，公司电脑的“导出”工作完成，但**先不要删除公司电脑上的项目**。必须等笔记本完成测试后再清理。

---

# 第二部分：个人笔记本操作

## 第 1 步：安装所需软件

在笔记本安装：

1. Git；
2. GitHub Desktop；
3. Python 3.12（安装时勾选 `Add Python to PATH`）；
4. Codex 桌面版；
5. VS Code（推荐，但不是必须）；
6. Docker Desktop（暂时可不装，只有以后运行 MySQL/Redis 容器时才需要）。

安装后打开 PowerShell，检查：

```powershell
git --version
py -3.12 --version
```

只要两条命令都能显示版本号即可。

---

## 第 2 步：在 GitHub Desktop 登录你的 GitHub 账号

1. 打开 GitHub Desktop；
2. 登录能访问私有仓库 `zhangkai333/finance-insight-agent` 的 GitHub 账号；
3. 不要把 GitHub 密码或验证码发给任何聊天工具；
4. 如果仓库是 Private，只要登录正确账号就能看到。

---

## 第 3 步：把代码克隆到笔记本

### 推荐方式：GitHub Desktop

1. 点击 **File → Clone repository**；
2. 在 **GitHub.com** 页签中选择 `zhangkai333/finance-insight-agent`；
3. Local path 建议设置为：

```text
C:\Users\你的用户名\Documents\GitHub\finance-insight-agent
```

4. 点击 **Clone**；
5. Clone 完成后，在 GitHub Desktop 中选择 **Repository → Open in PowerShell**。

### 如果 GitHub Desktop 中看不到仓库

可在 PowerShell 中执行：

```powershell
cd "$HOME\Documents\GitHub"
git clone https://github.com/zhangkai333/finance-insight-agent.git
cd .\finance-insight-agent
```

如果提示登录，按 GitHub 弹出的浏览器授权流程完成登录。不要在聊天中发送令牌。

---

## 第 4 步：确认克隆的是正确项目

在笔记本项目目录执行：

```powershell
git status --short --branch
git remote -v
Get-ChildItem
```

应该看到：

- 分支为 `main`；
- remote 指向 `zhangkai333/finance-insight-agent`；
- 根目录中有 `src`、`tests`、`scripts`、`docs`、`README.md`、`pyproject.toml`。

刚克隆后看不到 `data` 中的私有数据库和 `资料待放入` 是正常的，因为它们没有上传 GitHub。

---

## 第 5 步：在笔记本重新创建 Python 虚拟环境

不要从公司电脑复制 `.venv`。在笔记本项目目录运行：

```powershell
py -3.12 -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,mysql]"
```

成功激活后，PowerShell 命令行前面通常会出现：

```text
(.venv)
```

以后每次重新打开 PowerShell，都先执行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
```

---

## 第 6 步：重新创建 `.env`，但不迁移 DeepSeek Key

在笔记本项目根目录执行：

```powershell
Copy-Item .env.example .env
notepad .env
```

打开后：

1. 找到 `DEEPSEEK_API_KEY=`；
2. 保持等号后为空；
3. 其他路径配置先保留 `.env.example` 的默认值；
4. 保存并关闭。

正确形式类似：

```text
DEEPSEEK_API_KEY=
```

### 关于以后使用大模型

- 迁移和运行大部分本地测试不需要 DeepSeek Key；
- 如果以后确实需要调用 DeepSeek，建议在个人账号中重新创建或轮换一个新 Key；
- 只手工写入笔记本本地 `.env`；
- 不要把 Key 发给 Codex、聊天窗口、截图、README、GitHub Issue 或提交记录；
- 不要使用公司电脑上的旧 `.env`。

检查 `.env` 没有被 Git 跟踪：

```powershell
git status --short
```

正常情况下不应显示 `.env`。

---

## 第 7 步：接入移动硬盘并导入全部私有数据

把移动硬盘插入笔记本。假设它仍然是 `E:`。

先找到迁移包名称：

```powershell
Get-ChildItem -LiteralPath "E:\FinanceInsightBackup" -Directory
```

然后把下方 `时间戳` 替换为真实目录名：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\import_transfer_bundle.ps1 `
  -BundlePath "E:\FinanceInsightBackup\finance-insight-transfer-时间戳" `
  -CopySourceDocuments
```

### 绝对不要添加

```powershell
-CopyEnv
```

导入脚本即使收到该参数也会直接拒绝，不会导入 `.env`。

脚本会先根据 `manifest.sha256.json` 校验每个文件。成功时应看到：

```text
Checksum verification passed.
Bundle imported into: ...
The import did not copy .env or API keys.
```

导入后检查：

```powershell
Get-ChildItem -LiteralPath .\data -Force
Get-ChildItem -LiteralPath '.\资料待放入' -Force | Select-Object -First 10
```

应该能看到两个 SQLite 数据库及 `artifacts`、`evaluation`、`logs`、`processed`、`selected` 等目录。

> 如果提示“`资料待放入` 已存在”，不要强行覆盖。先把笔记本现有目录改名为 `资料待放入_旧`，再重新导入。

---

## 第 8 步：运行完整检查

确保虚拟环境已经激活，然后执行：

```powershell
$env:PYTHONPATH = Join-Path $PWD "src"
$env:PYTHONUTF8 = "1"

python -m compileall -q src scripts tests
python -m pytest -q
```

本项目在公司电脑上的基准结果是：

```text
30 passed
```

如果笔记本也是 `30 passed`，说明代码、环境和数据库基本迁移成功。

> GitHub Actions 当前可能仍失败，已知原因是 CI 临时环境缺少 Demo 数据初始化；这不等于笔记本迁移失败。它适合作为笔记本上 Codex 的第一个修复任务。

---

## 第 9 步：启动本地 API

保持当前 PowerShell 不关闭，执行：

```powershell
python -m uvicorn finance_insight.api:app --host 127.0.0.1 --port 8000
```

另开浏览器访问：

```text
http://127.0.0.1:8000/docs
```

如能看到 FastAPI 接口文档，说明服务已经启动。

停止服务时，在 PowerShell 中按：

```text
Ctrl + C
```

---

## 第 10 步：在笔记本 Codex 中打开项目

1. 打开 Codex；
2. 选择 **Open Folder / 打开文件夹**；
3. 选择：

```text
C:\Users\你的用户名\Documents\GitHub\finance-insight-agent
```

4. 确认 Codex 的工作目录是该项目根目录；
5. 不要把 `.env` 内容粘贴给 Codex。

可以把下面这段作为笔记本 Codex 的第一条消息：

```text
这是我的 finance-insight-agent 项目。以后这台笔记本是唯一开发电脑。
请先阅读 README.md、CONTEXT.md、PROJECT_REQUIREMENTS.md，以及 docs 下的架构、迁移、评估文档；
检查 git status、项目结构和测试方式，但不要读取或输出 .env，也不要寻找或显示任何 API Key。
先向我解释项目的业务目标、技术架构、Agent 工作流、RAG、数据层、测试体系和当前待办，
再帮我制定“继续优化项目 + Agent/AI 岗位面试准备”的分阶段计划。
```

---

# 第三部分：笔记本上的第一个 Codex 优化任务

迁移成功后，可把下面的任务发给笔记本 Codex：

```text
请修复 GitHub Actions CI。当前 CI 在干净的 GitHub 临时环境中因为缺少 data 目录和 SQLite Demo 数据而失败，
主要错误是 sqlite3.OperationalError: unable to open database file。
请先检查 .github/workflows/ci.yml 和 scripts/init_demo_data.py，
在运行测试前初始化合成 Demo 数据，然后本地模拟验证相关测试。
不要提交数据库、.env、原始资料或任何 API Key。
修改完成后向我解释失败原因、修复原理、验证结果，以及面试中如何讲这个问题。
```

预期修复方向是在 CI 测试前增加：

```yaml
- name: Initialize synthetic demo data
  run: python scripts/init_demo_data.py
```

不要只复制这两行就结束，应让 Codex 检查 YAML 位置并运行验证。

---

# 第四部分：确认笔记本完全可用后，再清理公司电脑

只有下面所有条件都满足，才开始清理公司电脑：

- [ ] GitHub 仓库在笔记本可打开；
- [ ] 笔记本成功 Clone；
- [ ] 私有迁移包 SHA256 校验通过；
- [ ] `data/` 和 `资料待放入/` 已导入；
- [ ] 笔记本测试通过；
- [ ] FastAPI 可以启动；
- [ ] 已在笔记本 Codex 中打开项目；
- [ ] 重要文件在移动硬盘上仍有一份备份。

满足后，在公司电脑进行：

1. 退出 Codex 账号；
2. 退出 GitHub Desktop；
3. 退出浏览器中的 GitHub 和 DeepSeek；
4. 如果 DeepSeek Key 属于你个人，建议在个人控制台轮换或撤销旧 Key；
5. 按公司规定清理 Windows 凭据、浏览器下载记录和个人登录；
6. 使用文件资源管理器删除公司电脑上的项目目录，并清空回收站；
7. 删除公司电脑上单独保存的迁移包；
8. 不要删除移动硬盘和笔记本上的备份。

> 清理前请遵守公司的设备和数据管理制度。如果公司要求由 IT 清理，交给 IT 处理，不要自行绕过公司政策。

---

# 第五部分：常见问题处理

## 1. `py -3.12` 找不到

尝试：

```powershell
python --version
```

如果 Python 版本是 3.11 或 3.12，可使用：

```powershell
python -m venv .venv
```

如果也找不到，需要重新安装 Python，并勾选 `Add Python to PATH`。

## 2. PowerShell 提示禁止运行脚本

只对当前窗口临时放行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

然后重新激活：

```powershell
.\.venv\Scripts\Activate.ps1
```

## 3. `pip install` 失败

先升级 pip：

```powershell
python -m pip install --upgrade pip
```

再重新安装：

```powershell
python -m pip install -e ".[dev,mysql]"
```

## 4. 导入时提示校验失败

说明移动硬盘中的某个文件复制不完整或已损坏。不要跳过校验：

1. 删除笔记本中本次导入的不完整数据；
2. 回公司电脑重新生成迁移包；
3. 重新安全弹出移动硬盘；
4. 再导入一次。

## 5. 测试不是 `30 passed`

把以下信息发给笔记本 Codex，但不要发送 `.env`：

```powershell
python --version
python -m pip --version
git status --short --branch
python -m pytest -q
```

只发错误输出，不要粘贴任何 Key。

## 6. FastAPI 启动后无法访问

确认 PowerShell 中服务没有报错，并访问：

```text
http://127.0.0.1:8000/docs
```

不要使用 `https`。如果 8000 端口被占用，可临时换成：

```powershell
python -m uvicorn finance_insight.api:app --host 127.0.0.1 --port 8001
```

然后访问：

```text
http://127.0.0.1:8001/docs
```

---

# 第六部分：为了后续面试，迁移完成后按这个顺序理解项目

## 阶段 A：能用 2 分钟介绍项目

需要回答：

1. 项目解决什么业务问题；
2. 用户输入什么，系统输出什么；
3. 为什么需要 Agent，而不是普通问答；
4. 为什么需要 RAG；
5. 数据从哪里来，如何进入数据库和向量检索；
6. 如何验证答案不是“看起来正确”。

## 阶段 B：能画出完整架构图

至少能讲清：

```text
用户请求
  → FastAPI
  → 意图识别 / Agent 状态流转
  → 财务结构化查询 + RAG 检索
  → LLM 生成
  → 引用证据 / 图表 / 结果
  → 评估与日志
```

重点阅读：

```text
README.md
CONTEXT.md
PROJECT_REQUIREMENTS.md
docs/ARCHITECTURE.md
docs/API.md
docs/DATA_DICTIONARY.md
docs/EVALUATION.md
docs/ADR.md
```

## 阶段 C：能解释关键技术点

重点准备：

- Agent 和固定工作流的区别；
- LangGraph 中 state、node、edge 的作用；
- RAG 的切分、索引、召回、证据引用；
- SQLite、MySQL、Redis 分别承担什么职责；
- FastAPI 接口设计；
- 超时、重试、降级和 fallback；
- 单元测试、集成测试、CI 的区别；
- 如何防止 API Key 和私有数据进入 Git；
- 如何评估答案质量、证据完整性和幻觉。

## 阶段 D：准备真实工程案例

至少准备下面三个 STAR 案例：

1. **CI 失败修复**：干净环境缺少数据库，如何定位并通过可重复初始化修复；
2. **数据与密钥隔离**：为什么代码走 GitHub、私有数据走迁移包、Key 不迁移；
3. **Agent/RAG 质量优化**：如何通过测试集、证据链和评估报告判断优化是否有效。

以后每完成一个功能，都让 Codex额外输出：

```text
1. 这次修改解决了什么问题；
2. 为什么这样设计；
3. 有哪些替代方案；
4. 如何测试；
5. 面试官可能追问什么；
6. 我应该如何用自己的话回答。
```

---

# 最终完成检查表

## 公司电脑

- [ ] 最新代码和本文档已 Push 到 GitHub；
- [ ] 已用 `-IncludeAllLocalData -IncludeSourceDocuments` 生成迁移包；
- [ ] 迁移包没有 `.env`；
- [ ] 移动硬盘安全弹出；
- [ ] 尚未提前删除公司电脑项目。

## 笔记本

- [ ] Git、GitHub Desktop、Python 3.12、Codex 已安装；
- [ ] GitHub 私有仓库已 Clone；
- [ ] `.venv` 已重新创建；
- [ ] 依赖已安装；
- [ ] 从 `.env.example` 新建 `.env`；
- [ ] `DEEPSEEK_API_KEY` 为空或以后使用新 Key；
- [ ] 私有数据校验并导入成功；
- [ ] 测试通过；
- [ ] FastAPI 可启动；
- [ ] Codex 已打开项目；
- [ ] 开始修复 CI 并整理面试材料。

---

# 公司电脑现在立刻要做什么

按顺序只做三件事：

1. 在 GitHub Desktop 查看本次新增/修改的文档和迁移脚本；
2. Commit message 填写：

```text
docs: add secure one-time laptop handover guide
```

3. 点击 **Commit to main**，然后点击 **Push origin**。

Push 完成后，再执行本文“公司电脑第 3 步”生成移动硬盘迁移包。
