# 决策台账（拍板→落档→验证闭环载体）

> 纪律：每条拍板一行；完成（代码+文档+测试三落）才勾；评审时扫未勾项。
> 病根 G2 的修复机制：决策存在对话流里必丢，必须落文件。

## 已闭环

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

- [ ] VOD-KBQ（R0 网关+KB 查询端点）：文档已评审待定 → 代码增量未写（引擎侧）
- [ ] VOD-VOI（Java /external/voices）：文档已出 → E3 查重语义待实测修正 → 代码未写
- [ ] 多 key 防线（t_vod_api_keys/限流/吊销）：设计在 VOD-VOI 文档 → 未实现
- [ ] GitCode CI 门禁（push 跑 pytest）：未配置
- [ ] Hermes 真实 MCP 接入机制（当前 install 落点是占位路径，需确认 config.yaml/连接器方案）
- [ ] vendored 规则平铺 .md 的技能发现格式与 Hermes 技能目录规范对齐
- [ ] U1-U20 真引擎端到端（等引擎侧上线）
- [ ] VodTeam 仓转移（等管理员权限，不阻塞）
