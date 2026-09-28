"""冻结限域证书的原始文字证据。此模块中的时刻说明不参与排盘计算。"""

BIRTH_EVIDENCE = {
    "source_url": (
        "https://disc.static.szse.cn/disc/disk01/finalpage/2011-03-02/"
        "050c139f-7ab2-4714-a1bb-dcaa33d0d5c2.PDF"
    ),
    "published_at": "2011-03-02",
    "announcement_no": "深证上〔2011〕72号",
    "claim": "002561 的公开发行股票自 2011-03-03 起在深交所上市交易",
    "time_assumption": (
        "该公告只证明上市交易日期；排盘采用版本化 listing_open 规则推定当日 09:30，"
        "不声称观测到了首笔成交的准确时刻。"
    ),
}

LIMITATIONS = [
    "只认证 002561 在所列日期及对应 60 日结果窗口；W2 完整 5,868 身份仍为 COVERAGE_INCOMPLETE。",
    "日期基于独立 Tencent observed-index 日集合，不声称该文件是交易所官方日历。",
    "历史 ST 状态未纳入筛选或特征，不能据此作 ST 分层结论。",
    "该单股历史范围仅用于回溯描述和探索；confirmatory_research_eligible=false。",
    "出生日期由 raw 首条日线与上市公告交叉支持；09:30 是明确的 listing_open 假设，不是已观测首笔成交时间。",
    "公司行动核对使用冻结 Tushare 因子、Tushare dividend action ledger 与 raw 前收盘值；不代表独立发行人审计。",
]
