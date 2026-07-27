# BLOCKER · select 无法产出三个预注册操作点（2026-07-27）

## 结论（一句话）

Development sweep（17,712 规则 × 18 环境，train+dev）上**不存在**同时满足
预注册 conservative 门槛（逐模型降幅 ≤1.5pp、逐 benchmark ≤2.0pp、≥80% 环境
正节省）的规则；且任何具有正 token 节省的规则最低也要付出 **4.87pp** 逐模型
降幅——把正节省比例门槛放宽到 0.5 也不变。这是预注册协议中定义的硬阻塞：
不放宽门槛、不查看 test，等待负责人决策。

## 证据

采集与判分完好：18/18 环境文件数精确匹配；判分采用 robust grader
（62/2,736 个旧 flag 已修正并留审计）。sweep 全量 637,632 行指标，
`selection_candidates` 聚合 17,712 候选，Pareto 前沿 93 条。

| 指标 | 数值 |
|---|---|
| 全空间最小逐模型降幅 | **1.85pp**（entropy_budget_fraction 家族，但 q20 节省 = **−11%**，仅 2.8% 环境正节省） |
| 降幅分位数 | p1=3.37pp · p5=4.26pp · p25=10.7pp · 中位 20.1pp |
| 降幅≈0 的规则数 | **0**（规则空间里所有规则都会在某处触发并伤准确率） |
| 各家族最优降幅 | entropy 1.85pp（负节省）· window_share 4.87pp（q20≈0.003）· latest_persistence 8.20pp（q20≈0.097）· adaptive_event 9.70pp（q20≈0.045） |
| "≥3 条互异规则 + 正 q20 节省"的最低可达降幅 | **4.87pp**（psf 门槛取 0.8/0.7/0.6/0.5 结论不变） |

诊断脚本：`~/gv2_diag.py`、`~/gv2_diag2.py`（服务器），复用 `replay_rules.py`
的原始聚合函数，非独立实现。

## 已排除的替代解释

1. **续跑校验 bug**：已修（`main_seed` 弹出比较），17 单元测试通过。
2. **判分系统性误判**：已修 robust grader 并批量修正 flag；baseline 在 replay
   中由 `final_answer` 现场重算，不依赖采集期 flag。
3. **采集不完整**：文件数与 problem-id 清单逐环境核对通过，manifest 齐全。
4. **聚合实现分歧**：诊断直接调用 `selection_candidates`/`pareto_frontier`。

## 科学解读（供决策参考）

结果与 Stage 1–5 的 False Consensus 结论一致：窗口共识不是终局，早停的准确率
代价在 16K 长轨迹下依然存在。另一个结构性因素：dense@64、32-token probe 的
询问开销约占主轨迹的 50%，保守规则"少停但一直付 probe 钱"，节省转负。
这本身是一个可发表的负结果/校准结果。

## 解除阻塞所需的唯一决策（负责人任选其一）

A. **接受负结果作为主发现**：以"预注册空间无安全停机点"为论文主结果之一，
   confirmation 阶段改为验证该负结果（在 test 上评估各家族最优点，展示
   4.87pp/正节省的下界在 held-out seeds/模型上复现）。需要一个新的预注册
   附录写明该转向。
B. **修订协议**（新版本号重新预注册，train/dev 重跑 select，test 仍未触碰）：
   例如门槛改为 balanced ≤2.5/3.0pp + psf≥0.5、token_efficient ≤5.0/6.0pp，
   和/或将 probe 开销从节省定义中分离（报告 gross/net 两套）。
C. **扩展规则空间**（同样需重新预注册）：更稀疏 probe（interval 256/512）、
   更高 maturity 下限、答案形态过滤等，降低 probe 税与误触发。

在收到决策前：test、Llama-8B、32B 均未被读取；confirmation 未启动。
