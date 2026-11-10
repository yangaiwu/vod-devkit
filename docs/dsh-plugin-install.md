# dsh 反馈插件接入安装手册（dsh-vod-devkit）

适用：给 DeepSeek Harness（dsh）接入 VOD 用户反馈采集插件——输入框右上角
「反馈」按钮 + 弹窗提交，反馈进 VOD 引擎。

版本：dsh-vod-devkit 0.4.4（配套 vod-devkit 0.4.4）
实测环境：dsh 0.2.1-rc.5，Node ≥ 18，Linux/macOS

---

## 一、前置条件

1. 已安装 dsh CLI：
   ```
   npm i -g @deepseek-ai/dsh        # 需 pnpm；确认 dsh --version 有输出
   ```
2. 已有一个 dsh profile（如 web）：
   ```
   ls ~/.dsh/profiles
   ```
3. 准备两个值（安装时必填/确认）：
   - `产品名`：这条反馈归属的产品（生态看板口径，如 CodeArts），**无默认值**，
     装错=污染别的产品数据；
   - `引擎地址`：VOD 引擎根地址（形如 https://vod-dev.topxtopx.com），
     需引擎已部署 T7i 以上版本（外部 API /external/token、/external/voices、/external/meta）。

## 二、安装（三选一，推荐 A）

### A. 官方安装器（推荐，自动写配置）

```
npx vod-devkit@0.4.4 install --target dsh --profile web \
  --product CodeArts \
  --java-api-base https://vod-dev.topxtopx.com
```

> 在**任意空目录**执行（不要在 devkit 源码仓里跑——npx 会优先用本地包，
> 版本可能滞后、写出的配置是旧格式）。

做的事：`dsh plugin add dsh-vod-devkit` + 幂等写
`~/.dsh/profiles/web/cordis.patch.yml` 的归因/引擎配置（product、apiBase、uiBase、confirmWrites）。

### B. 一键脚本（离线渠道，需手工补配置）

```
bash /opt/vod-install/vod-install.sh web   # 或从 http://<分发机>/vod-install/vod-install.sh 取
```
脚本只做「装包 + 覆盖技能文件」，**不写配置**——装完必须按下面「三、配置」补
cordis.patch.yml，否则插件起来了但没有 product，UI 入口不激活。

### C. 手工安装

```
dsh plugin --profile web add dsh-vod-devkit@0.4.4
```
然后按「三、配置」写配置。

## 三、配置（cordis.patch.yml）

文件：`~/.dsh/profiles/<profile>/cordis.patch.yml`

```yaml
- insert:
    - id: vod-devkit
      name: dsh-vod-devkit
      config:
        product: CodeArts
        apiBase: https://vod-dev.topxtopx.com    # Node 工具半自用
        uiBase: https://vod-dev.topxtopx.com     # 浏览器半用；公网反代时见 §五
        confirmWrites: false
```

三条硬规则（实测踩过）：
1. **必须嵌套在 `- insert:` 下**（顶格的 `- id:` 会被 dsh 组合层静默丢弃，
   插件整个掉出组合树：banner、工具、UI 全消失）；
2. **`name: dsh-vod-devkit` 不能省**（靠它绑定浏览器半，省了=按钮不出现）；
3. 手工改完重启 profile。

## 四、验证（四项，缺一不算装好）

1. 启动 banner（工具半）：
   ```
   dsh --profile web --no-open
   ```
   日志应出现：
   `[dsh-vod-devkit] Registered 3 tools, apiBase=https://…, product=CodeArts`
2. 插件在册：
   ```
   dsh plugin --profile web list | grep vod
   ```
3. 页面入口（UI 半）：浏览器打开 dsh web，输入框右上角有「反馈」按钮，
   点击弹出「提交反馈」表单。
4. 端到端提交：填一句真实反馈 → 提交 → 收到「已收录，产品团队会看到这条反馈」。
   （回执里不显示编号，属正常。）

## 五、公网部署（nginx 反代）补充配置

dsh 默认只监听 127.0.0.1；对外发布需 `--trusted-host <公网域名或IP>`
（不在名单的 Host 会被 403），并用 nginx 反代：

```nginx
location /dsh/ {
    proxy_pass http://127.0.0.1:3180/;
    proxy_set_header Host $host;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 3600s;
}

# 浏览器半的同源 API 通道：绕开引擎 CORS 白名单
location /dsh/rest/ {
    proxy_pass https://vod-dev.topxtopx.com/rest/;
    proxy_ssl_server_name on;
    proxy_set_header Host vod-dev.topxtopx.com;
    proxy_set_header Origin "";          # 引擎 CORS 只认自家域名，不剥 Origin 会 403
    proxy_http_version 1.1;
    client_max_body_size 1m;
}
```

公网形态下把配置里的 `uiBase` 改成同源前缀：
```yaml
        uiBase: /dsh        # 页面实际请求 /dsh/rest/...，由 nginx 转到引擎
```
（`apiBase` 保持引擎绝对地址，它只给 Node 工具半用。）
直接给远端绝对 `uiBase` 的症状：页面 console 报
`blocked by CORS policy … origin http://<公网IP>`，提交必失败。

## 六、常见问题

| 症状 | 原因 | 处理 |
|---|---|---|
| 启动日志无 `Registered 3 tools` | 配置块没嵌套在 `- insert:` 下 / product 缺失 | 按 §三 改 YAML 后重启 |
| 页面有 dsh 界面但无「反馈」按钮 | ① name 行缺失；② 装机副本旧（<0.4.4）；③ Host 不在 trusted-host | `dsh plugin list` 看版本；0.4.4 起已修 dock 槽名跨版本漂移 |
| 提交报「已暂存本机稍后重试」 | uiBase 缺失/不可达，浏览器请求落到 dsh 同源 404 | 按 §五 配同源通道或绝对 uiBase |
| console 报 CORS blocked | 跨域直连引擎，引擎白名单不含该 Origin | 用 §五 同源反代 |
| 提交 401「未提供 API Key」 | 令牌接口不可达（域名/证书/代理） | 浏览器直接打开 `<引擎>/rest/.../external/meta` 应返回 200 |
| 重启后页面一直 `connection lost` / `ws failed` | 旧页面的会话 cookie 随重启失效 | 用新 token 的 URL 重开页面 |
| 装完运行 `dsh plugin` 后被回滚成旧版 | profile 的依赖 specifier 钉在旧 tgz | 用 `dsh plugin --profile web add dsh-vod-devkit@0.4.4` 重装 |

## 七、升级 / 卸载

升级：
```
dsh plugin --profile web add dsh-vod-devkit@<新版本>
```
卸载：
```
dsh plugin --profile web remove dsh-vod-devkit
# 再手工删除 cordis.patch.yml 里 id: vod-devkit 的 insert 块
```

## 八、交付物清单

- npm 包：`dsh-vod-devkit@0.4.4`（插件本体）、`vod-devkit@0.4.4`（含安装器与 MCP 半）
- 技能文件：`vod-feedback-collect`（拷到 `~/.dsh/profiles/<profile>/skills/`）
- 支持渠道：VOD 运营；引擎接口变更需双方对账（当前外部 API 三个端点见 §一）