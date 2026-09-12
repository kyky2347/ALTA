# ALTA

## Autonomous LLM Trading Asterism

_由专业 LLM Agent 协作运行的虚拟交易平台。_

[![CI](https://github.com/kyky2347/ALTA/actions/workflows/ci.yml/badge.svg)](https://github.com/kyky2347/ALTA/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![用途：仅限研究](https://img.shields.io/badge/use-research--only-orange.svg)](docs/research-scope.md)

[English](README.md) · [繁體中文](README.zh-HK.md) ·
[快速启动](#本地运行) · [系统架构](docs/architecture/overview.md) ·
[验收记录](docs/audits/console-readability-2026-09-12.md) · [网站](https://alta.silment.com)

**交易的是机会；股票、ETF 或期权，只是兑现机会的载体。**

ALTA 是一套在本地运行的多 Agent 市场研究系统，包含操作看板、内部模拟和独立的券商执行模块。
四类 Scout 主动寻找线索，独立评审检验假设，交易方案 Agent 比较如何利用机会。
从研究到决策，每次交接都有记录可查。

目标是一家虚拟研究机构，而不只是推荐股票的聊天机器人。
判断一条线索是否有价值，要看它能否经得起证据、反对意见、成本和时间的检验。

> [!IMPORTANT]
> 本项目是实验性研究软件，不是投资建议、订单管理系统或盈利证明。
> 自主执行支持内部 **Shadow Paper** 和明确授权的 **Tiger 模拟盘**。
> 其他券商连接器属于独立、尚未完成的集成，不是已启用的自主实盘交易。

## 看见系统如何工作

当前版本看板，展示近期已保存的研究记录和专业研究团队。
点击图片可查看完整尺寸；研究假设不等于已批准交易。

[![机会工作台](docs/assets/alta-operator-console-zh.jpg)](docs/assets/alta-operator-console-zh.jpg)

| 研究团队                                                                                | 机会内部                                                                                              |
| --------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| [![Agent 协作](docs/assets/alta-agent-desk-zh.jpg)](docs/assets/alta-agent-desk-zh.jpg) | [![机会证据](docs/assets/alta-opportunity-detail-zh.jpg)](docs/assets/alta-opportunity-detail-zh.jpg) |
| 独立评审的分工、模型与已记录工作。                                                      | 原始决策摘要，可在看板追查完整记录。                                                                  |

| 券商连接                                                                                              | 模型分工                                                                                            |
| ----------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| [![券商配置](docs/assets/alta-broker-connections-zh.jpg)](docs/assets/alta-broker-connections-zh.jpg) | [![Agent 模型设置](docs/assets/alta-model-settings-zh.jpg)](docs/assets/alta-model-settings-zh.jpg) |
| 六家券商各自的配置表单，密钥保存与执行权限分离。                                                      | 按角色选择模型，保留独立评审。                                                                      |

2026 年 9 月 12 日 · 简体中文界面 · Agent 原始产物保留其撰写语言。
截图范围、记录 ID 和图片哈希见[发布验收记录](docs/audits/console-readability-2026-09-12.md)。
不包含密钥或账户资料。

## 这家虚拟机构如何协作

```mermaid
flowchart LR
    R["主动研究<br/>线索 → 证据 → 假设"] --> J["独立检验<br/>辩论 → 排序 → 交易方案"]
    J --> G{"独立审计<br/>与执行检查"}
    G -->|满足条件| E["行动与观察<br/>执行 → 监控 → 退出"]
    G -->|条件不足| W["等待<br/>记录缺少的证据"]
    W -. "带着具体问题跟进" .-> R
    E -. "结果归因与 Trader Mind 更新" .-> R
```

**LLM 决定什么值得研究，程序决定什么可以改变持久状态或资金。**
任何 Agent 都不能包办证据、风险批准和资金操作。证据不足时等待，不临场编造。

| 层次   | 已有实现                                                                                    |
| ------ | ------------------------------------------------------------------------------------------- |
| 发现   | 4 类 Scout、13 个有边界的只读工具，日期感知搜索、发行人网站抓取、订阅源、学术与历史档案检索 |
| 判断   | 独立模型路由、可证伪假设、反证、考虑组合的排序与载体比较                                    |
| 连续性 | 持久化跟进问题、催化事件期限、检查点恢复与 Trader Mind 演化                                 |
| 评估   | 时点冻结预测、前瞻结果、相对基准表现与只能下调风险的校准                                    |
| 运维   | 三语看板、API/SSE、运行历史、只写密钥、模型设置与启停控制                                   |

Scout 每次尝试默认 **11 次工具调用、196k 按系统预算口径计入的 Token、420 秒**，仍有硬上限。
结构化草稿可在原研究上下文内修正一次，沿用预算、精确引用并留下审计记录。
证据过期或不足仍需等待，不以增加重试次数代替当前有效信号。
增加预算用于补证，不是增加机会数量的配额。数据源有节流、取消和分层超时，
不完整的检索结果仍会标注。[检索设计与实测限制 →](docs/audits/research-retrieval-review.md)

### 四类研究者，不是四份相同的报告

Scout 共用工具，但不共用一份研究议程。每个 Scout 从自己的 Trader Mind 出发，
带着研究风格、关注方向和过往经验，主动搜索、追踪线索，而不只是总结推送来的新闻。

| Scout      | 主要追问什么                                               |
| ---------- | ---------------------------------------------------------- |
| 变化与事件 | 公告、业务或催化事件到底发生了什么变化？是什么时候发生的？ |
| 市场错位   | 价格或相关资产为何出现分化？这种差异有没有合理解释？       |
| 因果与政策 | 政策和产业变化会沿着什么路径，影响其他公司或行业？         |
| 预期差     | 市场似乎在期待什么？哪些证据可能推翻这些期待？             |

新闻只是入口。Agent 还可以查发行人网站、公告、公开数据、行情和其他网络来源。
刚抓取的网页不等于刚发生的事件：系统区分事件时间和获取时间。
社交媒体和二手报道提供的是线索，不能仅凭一段有说服力的总结就当成已核实的事实。

### 先弄清机会，再决定买什么

ALTA 把**投资假设**与**交易方案**分开保存。机会需要说明：什么变了、
市场预期可能错在哪里、什么证据能推翻判断，以及影响可能在何时兑现。
随后才比较可用工具、方向、成本和仓位；结果可以是股票、ETF、已支持的期权方案，也可以不交易。

```text
候选线索          机会假设             决策                结果
来源 + 时间  →  逻辑 + 证伪条件  →  评审 + 交易方案  →  监控 + 退出
     └──────── 关联 ID、引用和事件记录贯穿全程 ────────┘
```

这样做是因为，最直观的标的未必适合交易：流动性可能不足、价格可能已经变化，
几条看似不同的机会也可能暴露于同一种风险。好故事不能替代新鲜报价、组合检查和独立审计。
条件不足时，系统保存等待理由与跟进问题，不把“没有下单”视为必须消除的故障。

### 看板不只告诉你数量

| 你想弄清的问题           | 去哪里看                          |
| ------------------------ | --------------------------------- |
| 为什么会有这条机会？     | 机会详情中的摘要、证据和原始记录  |
| 谁研究过，谁有不同意见？ | Agent 工作台、模型分工和关联评审  |
| 当前状态之前发生过什么？ | 活动历史与可回看的事件时间线      |
| 现在能不能执行？         | 决策状态、执行模式和授权检查      |
| 哪些地方需要人处理？     | 系统健康、连接状态和 API 验证结果 |

英文、简体和繁体界面使用相同的操作逻辑与记录 ID；Agent 写下的研究内容保留原语言。
快照数量、已完成工作和正在运行的 Agent 分开显示。
卡片更多不代表独立机会更多，更不代表收益更好。

## 系统如何搭在一起

```mermaid
flowchart TB
    UI["React 三语看板"] <-->|"鉴权后的操作与查询"| N["Node 网关<br/>启动 · 凭证 · 受控工具"]
    N <--> P["Python 研究服务<br/>调度 · 研究流程 · API/SSE"]
    P <--> C["Codex App Server<br/>专业 LLM 会话"]
    P <--> DB[("PostgreSQL<br/>研究记录 · 事件 · 检查点")]
    P --> X["隔离的执行模块<br/>Shadow / 已授权 Tiger 模拟盘"]
```

浏览器负责展示和操作，不负责维持研究循环。受管后端负责调度与恢复，
PostgreSQL 保存工作记录，关闭标签页不会抹掉研究；进程重启后也有记录可供恢复。
改装的 Codex harness 提供 Agent 会话和工具调用，ALTA 负责研究流程与执行规则。
Redis 辅助协调，但不代替正式账本。

它适合研究多 Agent 判断机制、搭建可审计金融工作流，以及持续评估投资假设。
它不是低延迟交易引擎，也不是开箱即用的机构交易基础设施。
目前可验证的是从研究到模拟执行的可检查流程；有没有投资优势，需要靠后续真实结果证明。

## 本地运行

**前提：**macOS 或 Linux、Node.js 22+ 与 npm、Python 3.12、`uv`、
Docker/OrbStack 和足够磁盘空间。首次安装需要联网；
构建固定版本的自定义 harness 还需要对应 Rust 工具链。

```shell
git clone https://github.com/kyky2347/ALTA.git
cd ALTA
npm run dashboard
```

该指令会在需要时安装锁定的前端依赖、构建当前看板，并打开本机已鉴权页面。然后：

1. **API 连接**：填写自己的供应商密钥；保存后不会回显。
2. **Agent 协作 → Agent 模型**：指定可用模型；相互独立的评审角色必须使用不同模型。
3. **启动**：准备锁定的后端环境，启动受管依赖和研究服务。
4. **停止**：安全结束研究服务，并停止受管数据库与缓存。

券商交易权限默认关闭，需要单独授权；保存密钥不等于允许交易。
harness、供应商要求和排障步骤见[部署指南](docs/operations/getting-started.md)。

**第一次启动后，应该看什么？** 服务健康不代表正在研究，它可能在等待下一个周期。
研究开始后，先打开 Scout 记录、查看引用，再比较评审意见。候选线索不等于已批准机会，
假设获认可也不等于可以立即下单。建议先用 Shadow Paper，沿着记录看懂决策，再考虑授权券商。
模型访问权限、行情订阅资格和可用资金各有自己的要求，启动程序不能仅凭一把 API key 推断这些条件。

如希望手动安装依赖，先运行 `corepack pnpm install --frozen-lockfile`，再运行 `./alta dashboard`。

### 不使用付费 API 的验证

```shell
./alta env setup --dev
./alta test
./alta env python -m pytest -q alta-runtime/python/tests
uv run --frozen --project alta-runtime/capital-python pytest -q alta-runtime/capital-python/tests
uv run --frozen --all-extras --project alta-runtime/broker-python pytest -q alta-runtime/broker-python/tests
node --test alta-dashboard/tests/*.test.mjs
corepack pnpm check
./alta env down
```

集成测试需要受管 PostgreSQL 环境；没有 `DATABASE_URL` 时直接运行 `pytest`
不等于完整验收指令。确定性演示、回放和干净源码安装见[复现说明](REPRODUCIBILITY.md)。

## 执行能力不等于交易权限

| 模式或边界   | 真实支持范围                                                                                                 |
| ------------ | ------------------------------------------------------------------------------------------------------------ |
| Shadow Paper | ALTA 管理内部成交、成本、持仓、观察和退出，不操作券商                                                        |
| Tiger 模拟盘 | 已有适配执行器；精确账户绑定、明确授权、最新审计与重启对账                                                   |
| 五家预适配   | Alpaca、IBKR、Futu/moomoo、Longbridge/Longport、Schwab：私有配置、供应商代码和只读检查，端到端账户验收待完成 |

新 Tiger 实盘连接器同样尚未验收。独立六券商模块已包含持久化的建仓、监控与退出内核，
但**尚未接入自主研究执行循环**。离线测试覆盖重启不重复下单、撤销开仓权限及
券商回执与持仓一致后才确认退出；这些测试不等于实盘验收。本地网关、OAuth、账户权限和核验不能靠
一个通用密钥输入框替代。[供应商矩阵与待完成工作 →](docs/broker-expansion.md)

## 为中断和恢复而设计

PostgreSQL 是事实来源，Redis 提供辅助状态。工作由带隔离令牌的单一所有者认领，
券商意图先持久化再提交，订单状态不确定时先对账、不盲目重试。
断连时前端保留最后有效快照，过期的控制请求不能覆盖已确认操作。

[最新界面验收](docs/audits/console-readability-2026-09-12.md)记录前端修复、完整一方测试和干净源码安装；
[研究验收](docs/audits/operator-scout-reliability-2026-09-12.md)单独记录真实无下单研究和鉴权 API 检查。
发布记录保留发现的问题、修复、最终结果和停止证据，
并不构成 24×7 可用性认证或盈利保证。

尚未证明：持续样本外 Alpha、所有断电场景、所有浏览器兼容性，以及其他券商真实账户的下单验收。

## 工程结构

```text
alta-dashboard/                React 看板 · English / 简体中文 / 繁體中文
alta-src/                      Node 网关 · 有边界工具 · 启停控制
alta-runtime/python/           研究生命周期 · PostgreSQL · API/SSE
alta-runtime/capital-python/   隔离的 Tiger 模拟盘执行器
alta-runtime/broker-python/    隔离的实验性连接器与执行库
vendor/openai-codex/            固定版本、保留归属的 Agent harness
docs/                          架构 · 运维 · 验收
```

[架构](docs/architecture/overview.md) · [操作指南](docs/operations/operator-console.md) ·
[持续运行手册](docs/operations/autonomous-shadow.md) · [安全](SECURITY.md) ·
[贡献指南](CONTRIBUTING.md) · [更新记录](CHANGELOG.md)

## 许可与来源

ALTA 自有代码采用 [Apache-2.0](LICENSE)。项目以修改过的固定版本
[OpenAI Codex](https://github.com/openai/codex)（Apache-2.0）作为本地 App Server/harness，
并使用单独授权的依赖和 API。保留上游声明；修改和依赖见
[ATTRIBUTION.md](ATTRIBUTION.md)、[NOTICE](NOTICE) 与[上游修改记录](vendor/openai-codex/CHANGES.md)。

独立维护，不由 OpenAI 或任何被提及的数据供应商、券商背书。
供应商条款、交易所数据权限和再分发授权仍需使用者自行确认。
