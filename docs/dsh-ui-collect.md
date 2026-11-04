# dsh 采集 UI（笑脸入口）设计 v1.0

引擎侧对应文档：VOD-Project docs/vod-issue-sync/{proposal,design}.md。
拍板 A1-A4 见引擎 proposal §二（bot 代提交/匿名过审实名自动/单仓/囤积端点）。

## 一、形态

dsh web 输入框增加笑脸按钮 → 弹出反馈表单 → 提交走
POST /external/voices（囤积，不触发分析）→ 引擎按档建 issue
（VOD-ISYNC）→ 回执展示。

## 二、前置验证结论（2026-11-04 源码/包实读）

1. **UI 扩展机制存在（实证）**：dsh 客户端插件体系=
   `dsh.client` 行注册 → node 半扫 /plugins/<id>/client.js 下发 →
   浏览器半 lazy CJS 模块表；UI 面=`@deepseek-ai/dsh-client-ui-slots`
   slot registry（register({name,children,store,inject}, Component)+
   chain 选择+CSS 注入）+ dsh-client-web-react/dsh-client-ui-primitives。
   即：插件可携带浏览器代码注册 UI 组件进 shell 槽位。
2. **未实证项 T-VER-1（P0）**：输入框区具体槽位名。槽位声明在 shell
   运行时组合，minified 前端不可静态抽取——真机 boot dsh web 后枚举
   SlotMap（window.__DSH_BOOT__+SlotCore），选 composer/输入区最近槽位；
   无可用槽位的降级路径=工具栏命令/斜杠命令打开同一表单。
3. **账号面（T-VER-2）**：本机 ~/.dsh 无凭据文件、boot 无 login 子命令
   ——dsh 账号体系存在性未证实。身份源按三层设计（§四），真机验证
   层1是否存在。

## 三、插件包结构（dsh/dsh-vod-devkit 扩展）

```
dsh/lib/
  index.js        # 现有 node 半：工具注册（不动）
  client.js       # 新增浏览器半：槽位注册+表单组件（package.json
                  #   exports["./client"] 声明，dsh.client 行自动下发）
  form.css        # 随 factory 注入（loader 管 style tag 生命周期）
```

client.js 职责（纯前端，无敏感面）：
- register 进输入区槽位：😊 Button 组件
- 点击 → 渲染弹窗表单（React，ui-primitives 基件）
- 提交 → fetch 经 dsh web API gateway 转发到 VOD
  （同源策略：浏览器不直连 VOD 域，走 node 半转发——凭据不出浏览器，
  node 半已有 VOD_JAVA_API_BASE/KEY 配置面）

## 四、身份源三层（捕获 DSH 用户账号）

| 层 | 来源 | 说明 |
|---|---|---|
| 1 | dsh 会话身份 API（待 T-VER-2 证实） | 若 dsh 暴露登录身份/会话 user，取脱敏 ID+昵称 |
| 2 | 凭据文件指纹 | ~/.dsh/.credentials.yaml 存在时取 key sha1[:8] 指纹（明文禁止出 node 半） |
| 3 | 表单自愿留名 | 用户可选填昵称/联系方式（弹窗明示用途，不强制） |

**知情同意**：表单含勾选项「随反馈附上我的昵称（{identity 摘要}）」
默认勾选、可取消——不静默外传（身份是数据不是信任，纪律沿用）。
三层全空 → 匿名提交（引擎按匿名档过审核队列，A2）。

## 五、voiceId 与幂等（UI 通道语义）

voiceId = `ext_dshui_{identity_hash[:8]}_{sha1(content)[:12]}`
- **确定性**（同用户同内容重试=同 voiceId，引擎查重折叠回执，不重复
  入库）；与 MCP 通道调用级 nonce 不同是**有意的**：UI 通道 identity
  是用户级维度，不违反 R1（不同用户同款反馈 identity_hash 不同，
  声量不吞）
- identity_hash 取层1/2 可得指纹，三层全空取本机安装指纹（install 时
  生成 UUID 落 profile config，稳定且不含个人信息）

## 六、表单与提交流程

字段：反馈内容（必填，≤2000 逐条校验）/ 场景（选填）/ 昵称（选填，
默认勾选附身份摘要）/ product（默认 DSH——dsh 采集 UI 的语境就是
dsh 产品反馈，用户可改）。
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

## 九、排期

T-VER（真机：槽位枚举+账号面证实）0.5 天 → client 半实现+表单 1.5 天
→ 联调（等 MR !152 部署）0.5 天 → 验收 I1-I12+U 侧用例 0.5 天。
