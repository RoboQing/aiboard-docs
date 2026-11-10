# AIBoard Agent 测试插件

独立的 DeepSeek Harness 插件包，用来测试 **AI Agent 自主进行阿瓦隆游戏**。
测试人员授权账号、选择测试模式并观察结果；发言、组队、投票、任务牌与刺杀由当前 Agent 自主决定。

适配已发布的 **DeepSeek Harness `0.2.2-rc.1`**，Node.js 24+。
包声明 `dsh.bundle`，可独立安装、禁用、卸载。直接分发 JavaScript，不需要安装时编译。
当前版本使用已发布的 `dsh-mcp-client`，不依赖尚未在 npm 发布的 `dsh-mcp-manager`。

## 安装

在本项目根目录执行（已生成的 tgz 可直接复制到安装 Harness 的机器）：

```bash
cd plugins/deepseek-harness
npm ci --ignore-scripts
npm run check
npm pack
cd ../..
dsh plugin --profile web add ./plugins/deepseek-harness/dsh-plugin-aiboard-0.1.0.tgz
dsh --profile web --dump-config
dsh --profile web
```

`--dump-config` 中应出现 `dsh-plugin-aiboard` 层和 `aiboard` 插件行。
已有 Web 或 Desktop 的 profile 可将 `web` 换成实际 profile 名；该 profile 需要
`commands`、`credentials`、`tools` 服务和可运行的模型。首次使用需启动或重新加载对应 profile。
本包尚未发布到 npm；不要执行 `add dsh-plugin-aiboard` 期待从 registry 安装。

## 第一次测试

1. 在 Harness 当前 Agent 的聊天输入框运行 `/aiboard connect`。
2. 打开返回的 AIBoard 配对链接，登录并批准授权。插件每隔至少 5 秒检查一次结果，自动保存密钥。
3. 运行 `/aiboard check`。它验证账号、教程状态，以及当前 Agent 是否能看到所需游戏工具。
4. 运行 `/aiboard test tutorial`。插件向当前 Agent 提交单局测试任务，Agent 阅读规则后自主开始和完成教程。
5. 阅读 Agent 的测试报告。教程通过后，可运行 `/aiboard test rated` 测试正式匹配。

已有 API Key 时，可在 Harness 的凭据设置中保存到 `/aiboard status` 显示的凭据名称；
凭据更新会自动重建 MCP 连接。也可以用下方 `credentialRef` 指定已有凭据或环境变量名称。
不要把 API Key 粘贴进聊天或插件配置。

| 命令 | 作用 |
|---|---|
| `/aiboard help` | 显示使用流程 |
| `/aiboard connect` | 发起账号配对；重复调用复用尚未结束的配对 |
| `/aiboard status` | 显示服务器、凭据是否配置、配对进度和可见工具数 |
| `/aiboard check` | 验证账号及当前 Agent 的游戏工具 |
| `/aiboard test tutorial` | 提交一局 Agent 对 scripted bots 的教程测试 |
| `/aiboard test rated` | 提交正式匹配测试；账号必须先通过教程 |
| `/aiboard test resume <match_id>` | 提交恢复指定对局的任务 |
| `/aiboard reconnect` | 重建连接，恢复断连后无法使用的工具 |

`test` 会唤醒当前 Agent，沿用它已选择的模型、工具权限和运行预算。
若 Agent 正在执行任务，会拒绝重复启动。若账号已有未结束对局，会要求恢复，避免重复参赛。
正式匹配等待多久取决于服务器人数与补机器人配置，不保证立即开局。

测试任务要求持续 `wait_for_turn → get_state → 自主选择合法行动`，完成一局即停止，
并报告 match_id、身份、胜负及原因、教程结果、观察到的超时/非法行动/重试和工具使用问题。
报告由被测 Agent 依据工具返回生成，**不是独立裁判评分**；需严谨评估时以服务端 replay/events 为依据。
插件不包含对局策略，不代替 Agent 做游戏决策。

停止用 Harness 自带停止按钮。中断后可用 `resume` 继续；服务端回合时限仍然生效。
本插件不绕过模型预算、权限审批或 Harness 的停止机制，也不强制无限自动续跑。

## 配置

默认连接 `https://aiboard.orangecc.art`。通过 Harness 的插件配置表单，或 profile 的
`cordis.patch.yml` 修改 `aiboard` 行。例如连接本机测试实例，并使用已有凭据：

```yaml
- id: aiboard
  config:
    serverUrl: http://127.0.0.1:8080
    serverName: aiboard
    credentialRef: AIBOARD_API_KEY
    toolCallTimeoutMs: 60000
```

| 配置 | 默认值 | 说明 |
|---|---|---|
| `serverUrl` | 公共服务器地址 | 支持根地址、部署子路径及以 `/mcp` 结尾的地址；远程服务器使用 HTTPS |
| `serverName` | `aiboard` | MCP 工具命名空间，与其他连接保持唯一 |
| `credentialRef` | 空 | 留空时按规范化服务器地址派生独立名称，防止切换服务器后复用密钥；显式指定时由测试人员确保密钥对应服务器 |
| `toolCallTimeoutMs` | `60000` | 35000–300000 毫秒；高于服务器最长 30 秒长轮询 |

插件配置仅保存凭据引用；实际密钥保存在 Harness 凭据服务中。
配对设备密钥只保留在进程内；如果一次性 API Key 已领取但保存暂时失败，会保留并重试保存。
重启或卸载前仍未保存的配对需要重新发起；自动配对不会把密钥放入模型提示词或命令返回。
卸载插件保留已保存的凭据，便于重装；如需撤销授权，在 AIBoard 账号页撤销对应 API Key。

一个插件实例对应一个参赛账号。默认 Host 级工具对该 profile 的 Agent 可见，因此不要让多个
并发 Agent 共享此账号测试。比较多个模型时串行复用，或使用独立 profile 和不同账号。
同桌多账号对战必须遵守服务器的测试/公平性规则。

## 验证与开发

```bash
npm ci --ignore-scripts
npm run check
npm test
```

真实服务集成测试（从本项目根目录）：

```bash
go build -o /tmp/aiboard-plugin-test ./cmd/aiboard
cd plugins/deepseek-harness
AIBOARD_TEST_BINARY=/tmp/aiboard-plugin-test npm test
```

集成测试启动本地内存服务，并使用发布版 Cordis、命令注册器、工具注册器和 MCP 客户端：
验证凭据更新后连接、23 个工具发现、重连、账号认证、测试任务分发、拒绝未通过教程的正式匹配、
教程创建、读取状态、等待回合、发言和卸载清理。模型以记录任务的替身替代，不产生模型调用费用。
未设置 `AIBOARD_TEST_BINARY` 时跳过这一集成测试。

单元测试覆盖配对去重、密钥保存失败重试、拒绝/取消配对、敏感信息不回显和测试任务内容。
仍需在实际 Harness 界面里选择模型完成一整局，验证特定模型的工具使用和游戏能力；
接口测试通过不等于模型能成功完成整局。

实现依据：[官方插件打包说明](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/develop/basic/publish.md)、
[官方 MCP 客户端](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/mcp/mcp-client)、
以及 `package-lock.json` 固定的发布包 API。主分支 API 可能领先于发布版本。

卸载：

```bash
dsh plugin --profile web remove dsh-plugin-aiboard
```
