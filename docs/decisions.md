# 决策台账（拍板→落档→验证闭环载体）

> 纪律：每条拍板一行；完成（代码+文档+测试三落）才勾；评审时扫未勾项。
> 病根 G2 的修复机制：决策存在对话流里必丢，必须落文件。

## 已闭环
- [x] 身份界定对表（2026-11-03）：归属/授权分离定稿；外部分析三处不采纳（HMAC/多租户/Gateway）；内容边界 ≤2000 落码（U32）；签名回执记 P2 前置
- [x] 动态元数据客户端（2026-11-03）：meta 拉取+24h 缓存+快照兜底+stale 标记；归因白名单改走 meta；S11-S13/U29-U31 落档
- [x] 方案 A（2026-11-03）：插件收敛为纯采集——workflow 三工具+kb_search 删除（git 留档），运营归 vod-system 前端；知识技能留 knowledge pack；P1 任务级 token 取消；单上游单写口
- [x] key 交付定稿（2026-11-03）：零字段自动令牌=入门（A/B/C 三案比对见 proposal 三·四，B 否决为入门因把门槛放在价值之前）；vod_auth_status+令牌自动获取+引导已实现（24 用例）

- [x] 插件形态=devkit 同构完整形态（installer/MCP/skills/packs/policy）
- [x] 运行形态=随 agent 进程拉起走内网 API
- [x] 写权限=confirm+条数上限
- [x] 溯源与宿主感知（manifest/verify/vod_devkit_info/clientInfo）
- [x] 独立成仓：直接于新仓开发（暂住 xiaowu2119，转移触发=团队协作或对外上架启动）
- [x] 核心语言=Python（判定与推翻条件见 design 三）
- [x] 契约单一事实源=contract/tools.schema.json
- [x] 反馈采集两项 A：独立囤积端点（引擎侧 VOD-VOI）+ 逐次 confirm
- [x] VOD-VOI 落点修正：Java /external/voices 复用 saveCollectRecord
- [x] 外部/内部分层：外部=反馈采集者（preset collect），分析发起=内部（preset full）
- [x] 审计修复 E1/E2（认证头+双后端，协议级测试锁定）、E4（护栏作用域）、G1（安装器技能全量+双 key 配置+preset）

## 进行中

- [ ] **公开上架时机（2026-11-03 拍板）**：等 VOD key 签发制落地后再公开；
      业务窗口急则白名单灰度（邀请制，不算完全公开，不阻塞验证）
- [ ] **遥测（2026-11-03 拍板：维持不做）**：未来若做，opt-in 默认关+
      明确告知+最小字段，不采集敏感内容；当前链条不依赖它

- [ ] VOD-KBQ（R0 网关+KB 查询端点）：文档已评审待定 → 代码增量未写（引擎侧）
- [ ] VOD-VOI（Java /external/voices）：文档已出 → E3 查重语义待实测修正 → 代码未写
- [ ] 多 key 防线（t_vod_api_keys/限流/吊销）：设计在 VOD-VOI 文档 → 未实现
- [x] GitCode CI 门禁：.gitcode/workflows/ci.yml 已提交（push/PR 触发 pytest），线上首跑待观察
- [x] Hermes 真实 MCP 接入：`hermes mcp add`（config.yaml mcp_servers）+ `hermes mcp test` 实测 6 工具全通过。三坑已修：①宿主过滤 env（PYTHONPATH 不透传）→server.py 自举 sys.path；②-m 在宿主 cwd 找不到包→args 用脚本绝对路径；③add 是交互式→input y 应答
- [x] vendored 规则改技能目录结构 skills/<name>/SKILL.md（vendor_rules.py+仓内迁移）
- [ ] U1-U20 真引擎端到端（等引擎侧上线）
- [ ] VodTeam 仓转移（等管理员权限，不阻塞）
