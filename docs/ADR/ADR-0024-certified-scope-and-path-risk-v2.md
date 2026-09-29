# ADR-0024：限域认证准入与可追溯路径风险指标

- **状态**：已接受(Accepted)
- **日期**：2026-09-28
- **影响**：W4 historical dataset、v2 event-study API、标签版本、历史研究页面与报告
- **关联**：[ADR-0004](ADR-0004-as-of-time-isolation.md)、[ADR-0013](ADR-0013-research-validity-boundary.md)、[ADR-0022](ADR-0022-versioned-research-v2-api.md)、[ADR-0023](ADR-0023-f5-preregistered-experiments.md)

## 背景

独立审计确认，早期 v2 查询能在请求超出认证日期时静默只统计数据集内子集；错误证券也可能被表述成样本不足。原 v2 页默认 `activation=any`，扫描跳转仅带因子映射，未绑定精确关系参与位置。收益统计缺少路径指标，股票历史页继续以 v1 结果为主。

当前限域证书只覆盖 002561/SZSE 的 1,513 个观察日期（2012-02-23 至 2018-05-14），只具探索性研究资格。修复必须先验证 query 与证书的逐字段绑定，不能让请求范围隐式收缩，也不能让显示和导出丢失实际条件。

## 决策

1. 每个可查询认证数据集必须有代码登记的固定 pin：dataset id/digest、W2 certificate id/SHA、W2 manifest SHA、security identity、观察日期上下界/数量、PIT 版本、birth-profile source 版本及 label 版本。Manifest 的证书副本、输入版本、范围、分片状态和 digest 必须与 pin 完全一致；任何不一致都 fail closed。
2. 查询前检查认证状态、请求证券、日期范围与完整版本组。认证范围外的部分或完整越界请求一律返回 `OUTSIDE_CERTIFIED_SCOPE`，原请求日期照常回显、计数为零、不得裁剪统计。证券未认证、数据集未认证、证书不匹配、版本不匹配、数据缺失、范围内无匹配事件和样本不足使用不同状态码/原因。
3. v2 条件支持精确 `ten_god_category`（只比较 `B_DAY_005.raw_value`，并绑定 `DAILY/day`），以及精确关系类型、来源/目标上下文、柱位与组件。多个条件统一按 AND 执行；多因子仍按证券-日期-因子观察计数，同时返回不同证券-日期数量，不改变既有统计单位。
4. 日期扫描目标日作为独立 `target_date` 传递；历史 `date_from/date_to` 保持数据集完整认证范围默认值，并允许用户在范围内调整。扫描至历史、页面实际执行条件和报告导出保留同一组条件字段。Fortune 时间轴提供可编辑日期范围、日期口径、精确十神类别与服务端关系目录条件；前端只传递和展示服务端确定的结果，不重算术数。
5. 标签版本升为 `w3-hfq-adjfactor-v3`。对每个已登记 horizon（1/5/10/20/60 个后续个股交易 bar）保存收益、benchmark、excess、MFE、MAE 与最大回撤。MFE/MAE 为事件日收盘之后至第 N 根 bar 的 adjusted high/low 相对事件日 adjusted close 的极值；最大回撤为事件日 adjusted close 加未来路径上的峰至后续谷最大非负跌幅。三者不是同一指标，也不得互相代用。
6. 缺少必要价格、因子、基准或完整 horizon 时保持 null/unavailable 并报告样本数和缺失数。样本最大收益/最大亏损仅来自固定 horizon 收益序列；盈亏比为平均盈利除以平均亏损绝对值，任一组不存在时为 null。零不充当缺失，无亏损时最大亏损为 null，不产生无穷比率。
7. W4 schema v2 新增全 horizon 路径标签；旧 v1 分片可继续只读，缺少的历史路径周期返回 null。写入只允许新 dataset id，不原地改写已发布 manifest。`/api/v1/**` 路径与响应保持兼容，旧股票历史结果页面明确标为 legacy，主研究结果读取同一 v2 API。
8. 限域 W4 的证书资格不扩张到完整 PIT universe，也不授予 confirmation/OOS 资格。W6 既有预注册、78 项样本不足结论及其 `NOT_RUN` 重采样记录保持绑定原冻结 dataset/protocol，不因新标签集而重写。

## 后果与限制

- 认证范围外请求会明确不可用，不返回看似完整但实际被裁剪的子集统计。
- 单证券限域可用于探索性描述；日期集合来源、股票池完整性、ST/暂停历史和首笔成交时刻仍受原 W2 证书限制。
- 单股样本可以算描述性 MFE/MAE/MDD，但不构成市场预测、OOS 或确认性研究证据。
- W6 的冻结实验不自动继承新 dataset，也不自动重复抽样检验。

## 接受依据

2026-09-28 的限域验收已满足本 ADR 的范围内接受条件，详情见 [`W0-W8-AUDIT-REMEDIATION-2026-09-28.md`](../research/W0-W8-AUDIT-REMEDIATION-2026-09-28.md)：认证范围/证券/版本/证书回归通过；扫描到历史查询及报告保留精确关系、十神与日期条件；v1 兼容并由 v2 页面展示；Fortune v2 时间轴日期/条件控件通过真实 API 与浏览器验证；v3 dataset 的 4,539 个盘面引用、7,565 个收益窗口和 22,695 个路径指标独立零容差复算一致。此接受只确认该限域软件契约及工程证据，不改变 002561 单证券探索性范围，也不授予确认性/OOS 研究资格。
