/**
 * 全局通用股票基础清单与字典常量。
 *
 * 遵循分层设计原则：放置于 lib/ 层，供 UI 组件与底层 Store 共同引用，
 * 避免 lib/ 模块反向依赖 components/ 中的 React 客户端组件。
 */

export interface StockSuggestion {
  code: string;
  name: string;
  exchange: string;
  listingDate?: string;
}

export const POPULAR_STOCKS: StockSuggestion[] = [
  { code: "600519", name: "贵州茅台", exchange: "SSE", listingDate: "2001-08-27" },
  { code: "000001", name: "平安银行", exchange: "SZSE", listingDate: "1991-04-03" },
  { code: "002008", name: "大族激光", exchange: "SZSE", listingDate: "2004-06-25" },
  { code: "300750", name: "宁德时代", exchange: "SZSE", listingDate: "2018-06-11" },
  { code: "002594", name: "比亚迪", exchange: "SZSE", listingDate: "2011-06-30" },
  { code: "000858", name: "五粮液", exchange: "SZSE", listingDate: "1998-04-27" },
  { code: "601318", name: "中国平安", exchange: "SSE", listingDate: "2007-03-01" },
  { code: "688981", name: "中芯国际", exchange: "SSE", listingDate: "2020-07-16" },
  { code: "600036", name: "招商银行", exchange: "SSE", listingDate: "2002-04-09" },
  { code: "300059", name: "东方财富", exchange: "SZSE", listingDate: "2010-03-19" },
];

export const KNOWN_STOCK_NAMES: Record<string, { name: string; listingDate?: string }> = {
  "002008": { name: "大族激光", listingDate: "2004-06-25" },
  "000001": { name: "平安银行", listingDate: "1991-04-03" },
  "000002": { name: "万科A", listingDate: "1991-01-29" },
  "600519": { name: "贵州茅台", listingDate: "2001-08-27" },
  "300750": { name: "宁德时代", listingDate: "2018-06-11" },
  "600036": { name: "招商银行", listingDate: "2002-04-09" },
  "000858": { name: "五粮液", listingDate: "1998-04-27" },
  "601318": { name: "中国平安", listingDate: "2007-03-01" },
  "002594": { name: "比亚迪", listingDate: "2011-06-30" },
  "688981": { name: "中芯国际", listingDate: "2020-07-16" },
  "600000": { name: "浦发银行", listingDate: "1999-11-10" },
  "601899": { name: "紫金矿业", listingDate: "2008-04-25" },
  "300059": { name: "东方财富", listingDate: "2010-03-19" },
  "600030": { name: "中信证券", listingDate: "2003-01-06" },
  "601012": { name: "隆基绿能", listingDate: "2012-04-11" },
  "000333": { name: "美的集团", listingDate: "2013-09-18" },
  "600276": { name: "恒瑞医药", listingDate: "2000-10-18" },
  "601888": { name: "中国中免", listingDate: "2009-10-15" },
  "002415": { name: "海康威视", listingDate: "2010-05-28" },
  "600887": { name: "伊利股份", listingDate: "1996-03-12" },
  "601166": { name: "兴业银行", listingDate: "2007-02-05" },
  "000651": { name: "格力电器", listingDate: "1996-11-18" },
  "600050": { name: "中国联通", listingDate: "2002-10-09" },
  "300014": { name: "亿纬锂能", listingDate: "2009-10-30" },
};
