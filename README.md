# 人机协作任务卡

本地优先的任务状态记录工具，提供 Python 命令行和只读网页。把目标、当前状态、工作项、人工审批、阶段记录和验收证据保存到同一张任务卡，方便人和 AI 交接、继续执行与复核。

**想把整个发布包直接交给 AI？** 请让它先读 [START_HERE.md](START_HERE.md)，并告诉它：“请先阅读入口说明，检查你的运行能力，帮我完成安装和示例验证。”入口说明会引导 AI 区分本机、临时运行环境与仅能阅读附件的情况。

当前版本：1.1.0。任务卡程序运行时仅使用 Python 标准库，无需 Node.js 或数据库。

**使用 AI 协作功能，需要用户自行准备可读取本地文件、执行终端命令的 AI 助手，并让它在本项目目录中工作。** 本程序负责保存任务状态和执行记录；理解需求、规划、操作实际项目及核验结果由外部 AI 助手完成。只启动网页不会启动 AI，也不会自动执行任务。

程序本身不调用模型 API、不需要模型密钥；外部 AI 助手所需的账号、订阅或 API 密钥由用户在该助手中配置，费用也由相应服务收取。当前未内置模型聊天、模型供应商配置、MCP 服务或后台自主执行器。

## 可选：AI 秘书与莱茵生命接口

v1.1.0 新增 [秘书接口扩展](integrations/rhine-secretary/README.md)：提供本机 Node.js 接口桥、TypeScript 客户端和接入协议。需要另行准备兼容的秘书后端与莱茵生命宿主；不是任务卡 CLI 自带的秘书服务，也不包含私人数据。接口桥运行需 Node.js 22+，原有任务卡程序仍只需 Python。

## AI 如何接入

当前接入方式是 **AI 助手调用本地 CLI**：

```text
用户提出目标并授权
        ↓
外部 AI 助手：理解需求、操作实际项目、检查结果
        ↕ 通过 taskctl 读取和更新
本地任务卡：目标、状态、审批、记录、证据
        ↓
只读网页：供用户查看进度与待确认事项
```

1. 准备支持本地文件读写和终端命令的 AI 助手，完成该助手自己的登录或模型配置。
2. 用助手打开本仓库目录，给予任务所需的文件和命令权限。操作其他项目或应用时，还需对应工具及授权；本仓库不提供那些连接器。
3. 要求助手完整读取 [AGENTS.md](AGENTS.md) 和 [AI 接入指南](docs/AI_INTEGRATION.md)。不同助手对项目规则文件的加载方式不同，不应假定会自动读取。
4. 先用虚构示例确认助手能调用 CLI、读取 JSON 并写回记录，再建立真实任务。
5. 用户提出“开始执行”或“继续执行”后，助手按任务卡和授权范围工作，逐阶段记录实际结果；需要确认的操作先创建审批并暂停。

详细步骤、可复制提示词、审批流程、数据边界和当前限制见 **[AI 接入指南](docs/AI_INTEGRATION.md)**。只有聊天能力、无法访问本地文件或终端的 AI，需要用户手动执行命令和传递结果，不能直接自动接入。

## 环境要求

- Python 3.10 或更新版本。
- macOS / Linux 可直接使用 `./taskctl`；其他环境可使用 `python -m taskcard.cli`。
- Git 为可选依赖，用于开始或继续任务时记录工作目录的 Git 状态。

## 快速开始：先运行任务卡程序

下载或克隆仓库后，在仓库根目录执行：

```bash
python3 -m taskcard.cli create --from examples/demo-card.json
python3 -m taskcard.cli list
python3 -m taskcard.cli show demo-card --json
python3 -m taskcard.cli serve --port 8787
```

打开 <http://127.0.0.1:8787>，可以查看任务、待审批操作、阶段记录和验收进度。按 `Ctrl+C` 停止服务。网页为只读视图，修改通过 CLI 完成；CLI 更新后需刷新网页。

示例创建一次即可，重复创建同一 ID 会报错。所有示例内容均为虚构，不包含真实项目记录。

## 走完一次演示流程

创建示例卡后执行：

```bash
./taskctl start demo-card --note "已读取示例卡并检查当前环境"
./taskctl show demo-card --json
```

确认输出包含示例目标、工作项和验收条件后，再记录这次实际观察：

```bash
./taskctl work demo-card work-1 --status done --result "已读取并核对示例卡字段"
./taskctl checkpoint demo-card --summary "完成示例卡读取核对" --verified "show --json 的输出包含目标、工作项和验收条件"
./taskctl evidence demo-card --criterion accept-1 --kind manual --description "已人工核对任务卡字段" --locator "task-cards/demo-card/card.json"
./taskctl verify demo-card
./taskctl complete demo-card
```

这段流程只演示记录与状态门禁，不代表完成任何真实业务任务。

## 常用操作

```bash
./taskctl --help
./taskctl continue <任务卡ID> --note "已重新读取任务卡并核对当前环境"
./taskctl set-state <任务卡ID> --current "当前真实状态"
./taskctl request-approval <任务卡ID> --action "待执行操作" --risk "操作影响" --work-item <工作项ID>
./taskctl approve <任务卡ID> <审批ID> --note "用户明确批准的内容"
./taskctl reject <任务卡ID> <审批ID> --note "用户拒绝的原因"
```

`approve` 只是保存审批记录，操作者必须先取得真实授权。程序不会自动执行审批所描述的操作。

数据目录默认是**当前工作目录**下的 `task-cards/`。可通过全局参数 `--home` 或环境变量 `TASKCARD_HOME` 指定；参数优先于环境变量：

```bash
./taskctl --home /path/to/local-cards list
```

请持续使用同一数据目录。创建新任务时复制 `examples/demo-card.json`，更换 ID 并填写真实目标、限制、授权边界及验收条件；自己的规格可放在被 Git 忽略的 `task-card-specs/` 中。示例使用 `ready`，省略状态则默认为 `draft`；当前 CLI 没有单独的 draft → ready 命令。

## 状态与验收

| 状态 | 含义 |
| --- | --- |
| `draft` | 讨论中，不能开始执行 |
| `ready` | 已准备开始 |
| `in_progress` | 执行中 |
| `waiting_approval` | 存在待处理审批 |
| `blocked` | 当前受阻 |
| `completed` | 已通过程序的完成检查 |
| `cancelled` | 已取消 |

`verify` 检查工作项是否全部为 `done`、是否存在待审批操作、验收项及证据引用是否齐全，以及环境快照和其中已检查的必需文件资源。`complete` 通过同一检查后才写入完成状态。`skipped` 工作项仍会阻止完成。

证据内容由操作者提供；程序不会验证证据描述是否真实，也不会自动访问证据 URL 或测试外部系统。环境快照记录文件是否存在、修改时间和 Git 状态，**不是文件备份**。

## 文件结构

```text
taskctl                  macOS / Linux CLI 入口
taskcard/core.py          状态、审批、证据与 JSON 持久化
taskcard/cli.py           命令行接口
taskcard/server.py        本地只读 HTTP 服务
taskcard/web/             网页 HTML、CSS、JavaScript
tests/                   单元测试
examples/demo-card.json  可公开的虚构示例
AGENTS.md                AI 在本项目中的任务执行约定
docs/AI_INTEGRATION.md    AI 接入步骤与可复制提示词
```

运行后生成的本地数据：

- `task-cards/<id>/card.json`：当前任务状态。
- `task-cards/<id>/events.jsonl`：追加式事件日志。
- `task-cards/<id>/snapshots/`：开始或继续执行时的环境记录。

JSON 文件使用临时文件替换；卡片、日志及快照之间没有事务保证，也没有多进程写入锁。当前适合单用户本地使用，避免多个写入者同时更新同一任务。

## 开发验证

```bash
python3 -m unittest discover -s tests -v
```

## 数据与发布边界

本仓库只发布程序、测试和虚构示例。真实任务卡、项目规格、快照、报告、备份、临时媒体及本地依赖已加入 `.gitignore`；这些文件仍保留在本机。忽略规则不能代替提交前检查，也不会移除已经进入 Git 历史的文件。

网页服务没有登录或权限控制，默认仅监听 `127.0.0.1`。API 会返回完整任务卡，请保持本地使用。该工具不包含自动发送消息、付款、发布或账户权限修改能力；审批记录也不是操作系统层面的安全隔离。

尚未选择开源许可证；公开仓库不等于已授予开源许可。正式开源前由项目所有者决定授权条款。
