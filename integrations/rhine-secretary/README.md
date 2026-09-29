# AI 秘书与莱茵生命：接口扩展

本目录是从现有联动实现中分离的通用接口代码，提供 Node.js 本机接口桥和 TypeScript 浏览器客户端。只包含秘书相关功能，不包含真实资料、数据库、采集器、模型配置或完整莱茵生命界面；不需要复制任何人的私人数据。

它是开发接入包，不是完整秘书软件，也不是一键安装的插件。任务卡 CLI 与秘书服务是两个独立程序：根目录的 taskctl 不会提供这里的秘书 API。接入方需要自行准备兼容的秘书后端和莱茵生命宿主。

## 文件

- `integration-bridge.mjs`：固定本机上游、路由校验、请求限制、读取合并和可选人工分类写入。
- `secretary-client.ts`、`shared-read-pool.ts`：浏览器侧数据校验、读取和写入客户端。
- `example-server.mjs`：可运行的只读连接检查页，未连接后端时显示失败，不制造演示结果。
- `bridge.test.mjs`、`client.test.cjs`：仅使用虚构数据的自动检查。
- `CONTRACT.md`：后端需要满足的接口协议。

## 最快检查

接口桥需要 Node.js 22 或更新版本，无运行时第三方依赖。前端源码需要 TypeScript 编译；单独运行检查页不需要编译器。

先启动自己的兼容秘书服务：固定监听 `http://127.0.0.1:8866`，提供 CONTRACT.md 中的 API。下载接口独立包后，在解压目录运行；若下载完整仓库，先进入 `integrations/rhine-secretary/`：

```bash
node example-server.mjs
```

用浏览器打开 `http://127.0.0.1:5180`，点击“检查秘书目录”。若该端口已被使用，可设 `RHINE_PORT=5181` 后启动。按 Ctrl+C 停止。服务未启动、协议不兼容或连接失败时，不表示安装成功。

## 集成现有莱茵生命宿主

将接口桥放入本机 Node HTTP 服务，在原有静态文件路由之前调用：

```js
import {createIntegrationBridge} from './integration-bridge.mjs';
const bridge = createIntegrationBridge({port: 5180});
// 在现有 http.createServer 的 async 请求处理函数中：
// if (await bridge(req, res)) return;
// 再继续原有静态页面处理。
```

宿主应只监听 `127.0.0.1`，端口必须与 bridge 的 port 参数一致。不要直接覆盖已有接口桥；若宿主已有 `/api/local/v1/capabilities`，由开发者合并秘书能力字段并保留原有检查。此模块不负责宿主的其他功能。

把两个 `.ts` 文件放到前端同一源码目录，通过现有 TypeScript/Vite 构建。前端可调用 `getCatalog()`、`getWidget('todo')`、`getRevision()`，以及详情与人工分类接口。所有请求必须通过宿主同源路径；不要绕过接口桥直连后端或增加宽泛 CORS。

人工写入默认关闭。只有确实需要用户点击分类、便笺或置顶，并完成权限和协议核对后，才使用 `createIntegrationBridge({port:5180, enableReview:true})`。`request_id` 使用 `crypto.randomUUID()`；写入超时后保留相同请求 ID 和正文核对/重试，不自动生成另一笔操作。409 冲突应重新读取并让用户核对。不能把成功收到 HTTP 响应当成业务验收完成。

## 数据边界

发布包没有业务数据，但接入运行后，秘书接口会返回接入者自己的事项和项目信息。它不是内容脱敏器，不会按行业识别或清除自由文本；需要严格限定运行时信息时，应在自己的秘书后端选择数据源与授权范围。

接口桥不读取桌面目录，不提供文件操作、付款、消息发送或采集控制。动作令牌只放内存，不应写进 URL、日志或仓库。接口安全检查不是用户登录系统，应保持本机使用，不开放公网。

## 测试与已知边界

```bash
node --test bridge.test.mjs
npx --yes --package typescript@5.9.3 tsc --strict --target ES2022 --module commonjs --lib ES2022,DOM,DOM.Iterable --outDir dist/secretary-client-test secretary-client.ts shared-read-pool.ts
node client.test.cjs
```

测试覆盖路由和请求边界、默认禁写、令牌检查、冲突与错误处理、会话刷新、读取失效和客户端解析。测试使用虚构数据，不接触真实秘书服务，不能证明所有莱茵生命版本都兼容。接入后仍需在自己的环境验证。
