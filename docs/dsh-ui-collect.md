# dsh 采集 UI（笑脸入口）设计 v1.0

引擎侧对应文档：VOD-Project docs/vod-issue-sync/{proposal,design}.md。
拍板 A1-A4 见引擎 proposal §二（bot 代提交/匿名过审实名自动/单仓/囤积端点）。

## 一、形态

dsh web 输入框增加笑脸按钮 → 弹出反馈表单 → 提交走
POST /external/voices（囤积，不触发分析）→ 引擎按档建 issue
（VOD-ISYNC）→ 回执展示。

## 二、前置验证结论（2026-11-04 真机 boot dsh web + 包实读）

1. **UI 扩展机制实证（T-VER-1 完成）**：本机 boot `dsh --profile web`
   实测。笑脸按钮落点=**`conversation.composer.dock`** 槽（输入框
   dock 区，多 entry 按 order 排，官方 activity pill 即注册于此）。
   注册模式（照抄官方插件）：
   `ctx.slots.inject("conversation.composer.dock", function* () {
     yield ctx.slots.register({ name, id, order, locale, inject },
                              SmileyButton); })`
   相邻槽：conversation.input.overlay（斜杠菜单）/input.attachments。
   浏览器半=client.js 经 dsh.client 行下发（/plugins/<id>/client.js），
   node 半不动——插件带 UI 是官方支持形态，**无降级路径需要**。
2. **账号面实证（T-VER-2 升级）**：dsh **有账号体系**——settings-account
   插件含平台授权 URL（login/authorize-url/browser-login）、
   account.view.status（credential-stored 等）、avatar/details 快照。
   身份源层1（会话身份）从「待证实」升级为「存在」：按 settings-account
   的 snapshot 模式对接（details/avatar/状态），凭据文件指纹（层2）
   降为未登录时的兜底，自愿留名（层3）不变。知情同意纪律不变。

## 三、插件包结构（dsh/dsh-vod-devkit 扩展）

```
dsh/src/client.jsx      # 源码：😊 按钮+弹窗表单+提交逻辑+账本（React）
dsh/lib/client.js       # 构建产物（esbuild transform→CJS+wrap_client.py 包装）
dsh/scripts/wrap_client.py  # 官方 factory 模式包装器（见下）
dsh/lib/index.js        # node 半：工具注册（不动）
```

**已实现并真机验证（2026-11-04）**：按钮渲染进 composer dock、弹窗表单
（内容≤2000 计数/场景/昵称+知情同意勾选）、提交真打网络、失败优雅降级
（引擎 !152 未部署→token 401→「已暂存本机稍后重试」+本地账本确定性键
ext_dshui_da8c0949_00c6757df23f）。

**构建坑（实测钉死，官方插件反编译对照）**：
- client 半判别字段=package.json `dsh.client: {platform: "web", inject: [...]}`
  （漏它→包不进浏览器仓单，node 半扫的就是这个字段）
- 浏览器半导出面必须含 `exports.inject = ["slots"]`（客户端服务名数组），
  缺它内核不激活（web boot 报 entry did not activate，整个前端起不来）
- React 不 vendor：`require("react")` 由 shell 模块表提供——esbuild 用
  transform 模式（`--jsx=automatic --format=cjs`），bundle 模式会把
  module.exports 提前求值到 factory 外导致注册即崩
- 浏览器直连 VOD：CORS 已通（VOD nginx 预检 200+ACAO 回显），零引擎新增
- config：`window.__VOD_DSH_UI_BASE__` 覆盖，缺省 https://vod-dev.topxtopx.com

## 四、身份=登录态二值（2026-11-04 用户纠偏：删手填昵称）

原三层设计里的「表单自愿留名」已删——用户反馈正确：昵称手填是账号体系
未证实时期的过渡产物。现在逻辑：
- **已登录** → 身份取自 dsh 账号（settings-account 快照：昵称/脱敏 ID），
  提交体带 user_masked，issue 的 on_behalf_of 用它
- **未登录** → 纯匿名（表单无任何身份字段，引擎按匿名档过审核队列）
- 本地账本键的 identity 维度用 localStorage 安装指纹（不外发）

v1（当前）：未登录路径实现完毕（表单只剩内容+场景）；登录态身份读取
（settings-account 服务注入方式）为 v1.1——需真机确认 client 半读取
账号快照的 API 通道后接入，不猜接口。

## 五、voiceId 与幂等（UI 通道语义）

voiceId = `ext_dshui_{identity_hash[:8]}_{sha1(content)[:12]}`
- **确定性**（同用户同内容重试=同 voiceId，引擎查重折叠回执，不重复
  入库）；与 MCP 通道调用级 nonce 不同是**有意的**：UI 通道 identity
  是用户级维度，不违反 R1（不同用户同款反馈 identity_hash 不同，
  声量不吞）
- identity_hash 取层1/2 可得指纹，三层全空取本机安装指纹（install 时
  生成 UUID 落 profile config，稳定且不含个人信息）

## 六、表单与提交流程

字段：反馈内容（必填，≤2000 逐条校验）/ 场景（选填）/ product（默认
DSH——dsh 采集 UI 的语境就是 dsh 产品反馈，用户可改）。身份=登录态
二值（见 §四），表单无身份字段。
提交：confirmed 语义内置（用户点「提交」按钮即逐次确认，无静默批量）；
单批 1 条（表单即单条，多反馈多开）。本地账本复用现有 submissions
（cap 200 环形），记 voiceId+issue_sync 回执。

## 七、回执（F2 说人话）

- 匿名档：「已收录，产品团队审核后会跟进」
- 实名档：轮询 GET /external/voices 的 issue_sync 节，
  CREATED→「已建 issue：{issue_url}」（用户可点开看自己反馈的单）
- voiceId 不展示（编号噪音），账本留 agent/日志侧对账用

## 八、护栏对齐

- 凭据读取：client.js/node 半继续不读 VOD_JAVA_API_KEY 之外的任何
  凭据；dsh 凭据文件只出指纹（层2），明文不落日志/请求
- 传输：node 半转发继承 vod_mcp 传输守卫（非回环强制 https，-32014）
- 内容：content ≤2000 逐条、sanitize 在引擎侧 issue 组装出口执行
  （VOD-ISYNC design §三），双层防线

## 九、排期（T-VER 已完成 2026-11-04）

client 半实现+表单 1.5 天 → 联调（等 MR !152 部署）0.5 天 →
验收 I1-I12+U 侧用例 0.5 天。

## 十、位置与形态迭代（2026-11-04 用户三连拍板）
- 删手填昵称：身份=登录态二值（未登录纯匿名；登录取账号快照 v1.1）
- 表单加分类 chips：参考官方 message-feedback 七分类（任务结果/指令理解
  与遵循/产品功能与交互/稳定性和速度/资源使用与费用/安全隐私与权限/
  其他），单选默认其他，落 description 前缀+账本 category
- 入口位置=**输入框右上角**（用户拍板）：官方 slot 体系无角位槽，实现=
  仍挂 composer.dock 槽作挂载点（合规），组件 JS 自算 contenteditable
  输入框矩形，fixed 定位到其右上角（x=input.right-32, y=input.top+5），
  ResizeObserver+800ms 兜底轮询跟随布局（会话切换/侧栏折叠）。脆弱性
  记档：依赖输入框选择器 [contenteditable=true]，官方改版需回归。
  图标 💬 悬停提示「反馈」，弱色常态/悬停加深（对齐官方 label 层级）

## 十一、实现状态（2026-11-04，多次迭代后收敛）

**已实现并真机验证**：
- 入口：输入框右上角 24px 图标（自定位：contenteditable 矩形+ResizeObserver
  +800ms 轮询兜底），SVG 内联图标零依赖
- 表单：自研 SelfModal/PrimaryBtn（**解耦：零官方组件依赖**，视觉参考
  官方 message-feedback；dsw CSS 变量在则跟主题、不在用硬编码兜底）
- 分类=VOD 引擎 v2.2 六类口径（无效问题不给选项），默认不选=引擎重判
- scene 独立字段（引擎契约 voices[].scene ≤128）
- **动态产品名**：文案/product/description 前缀三处统一走
  __VOD_DSH_UI_PRODUCT__ 注入（嵌入方装前设置），不注入=中性文案+
  不带 product（UNKNOWN 档，不静默猜）
- 身份=登录态二值：未登录纯匿名（v1）；v1.1 接 settings-account 快照

**构建/运行坑（全部实测钉死）**：
- crypto.subtle 只在安全上下文存在（https/localhost）——公网 http 访问
  undefined 崩溃；sha1Hex 加 FNV-1a 双种子兜底（账本键无密码学要求）
- 官方 client factory 三坑见 §三（dsh.client.platform 声明/exports.inject
  =["slots"]/React 不 vendor 走模块表，esbuild transform 模式）
- dsh web 公网暴露需 --trusted-host（browser-trust 栅栏，Host 不在名单 403）
- 测试盲区教训：127.0.0.1 验证是安全上下文，公网 http 的坑测不出

## 十二、场景用例（插件侧，对应引擎 proposal §八 S1-S7）

| # | 场景 | 插件侧行为 |
|---|---|---|
| U-S1 | 匿名首次反馈 | 提交→自动令牌→入库成功→回执「已收录，审核后建单」 |
| U-S2 | 实名反馈 | 提交成功→轮询 issue_sync→CREATED 时展示 issue 链接 |
| U-S3 | 断线失败 | 「已暂存本机，稍后重试」→下次打开 dsh 自动重提暂存行 |
| U-S4 | 重复提交 | 本地键同 voiceKey→账本去重；引擎侧 V9 updated 幂等 |
| U-S5 | 建单后崩溃 | 插件无感知（引擎折叠检索兜底）；回执轮询终会命中 |
| U-S6 | 运营拒绝 | 回执轮询命中 REJECTED→「反馈未采纳」 |
| U-S7 | 凭据内容 | 客户端不拦（原文保留）；引擎建 issue 出口 sanitize |
