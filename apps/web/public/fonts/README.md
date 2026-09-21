# 平台自带字体资源（apps/web/public/fonts）

本目录是**实际被浏览器加载**的字体资源，不是 font-family 回退列表。
目的是让"品牌宋体金色"这类视觉特征在 Windows / macOS / Linux 上一致，
而不是退到各系统自带的宋体（Windows 只有 SimSun，在大字号下与参考图差别明显）。

## 文件与来源

| 文件 | 来源 | 许可证 |
|---|---|---|
| `noto-serif-sc-subset.woff2` | Google Fonts · Noto Serif SC（可变字重 200–900）`NotoSerifSC[wght].ttf` | SIL Open Font License 1.1（见 `OFL-NotoSerifSC.txt`） |
| `noto-sans-sc-subset.woff2` | Google Fonts · Noto Sans SC（可变字重 100–900）`NotoSansSC[wght].ttf` | SIL Open Font License 1.1（见 `OFL-NotoSansSC.txt`） |

* 上游仓库：`https://github.com/google/fonts/tree/main/ofl/notoserifsc`、
  `https://github.com/google/fonts/tree/main/ofl/notosanssc`
* 下载时的源文件 SHA-256 前 16 位：
  `NotoSerifSC[wght].ttf` = `050080d9255a8680`，
  `NotoSansSC[wght].ttf` = `a3041811a78c361b`。
* 子集产物 SHA-256 前 16 位：
  `noto-serif-sc-subset.woff2` = `5562184d68bf7a31`，
  `noto-sans-sc-subset.woff2` = `e398de35ed43c512`。

**未使用任何系统专有字体**（PingFang SC / Songti SC / 微软雅黑 / SimSun 均未打包、未子集化、
未随仓库分发）。GoF/思源系（Source Han）与 Noto CJK 同源，OFL 允许子集化与再分发；
本目录保留原始 OFL 文本。

## 与参考图的关系（重要）

参考图是在 macOS 上渲染的，其字体文件**未提供**，因此：

* **无法、也不声称**已识别参考图使用的原字体；
* 选择 Noto Sans SC / Noto Serif SC 是因为它们是 OFL 授权下与参考图风格最接近、
  且可合法分发的替代字体；
* 因此"字体差异"在报告中如实列为**已知残余差异**，而不是宣称已 1:1 还原。

## 子集化配方（可复现）

字符集由 `output/fontwork/collect_glyphs.py` 生成（该脚本在本地检查产物目录，
不入库），来源为两部分：

1. `apps/web/**` 源码中的全部非 ASCII 字符；
2. **后端引擎输出**：遍历 2015–2030 每一天收集黄历字段（干支 / 建除十二值 /
   十二神 / 二十八宿 / 宜忌条目 / 神煞方位…）以及八字盘面的词表。

第 2 步不能省：宜忌、神煞这类文本**只在运行时出现**，源码里扫不到；
漏掉就会在页面上出现"一半自带字体、一半系统字体"的混排。

```bash
python -m fontTools.subset "NotoSerifSC[wght].ttf" \
  --text-file=subset-chars.txt --flavor=woff2 \
  --layout-features='*' --no-hinting --desubroutinize \
  --output-file=noto-serif-sc-subset.woff2
```

同样的命令用于 `NotoSansSC[wght].ttf`。子集大小：宋体 550 KB / 黑体 422 KB。

**已知缺失字形**：`▴ ▸ ▾` 与变体选择符 `U+FE0F`（U+25B4 / U+25B8 / U+25BE）。
Noto CJK 不含这些几何符号，它们会按 `font-family` 回退到系统字体。
这些字符只用于小尺寸的排序箭头，不影响中文与数字的渲染一致性。

## 字重策略

两个子集保留完整的可变字重轴，但 `@font-face` 只声明 `font-weight: 400 900`：

* 上游变量字体把轴的**默认值**设在最细端（宋体 200 / 黑体 100），
  若声明 `100 900`，一个 `font-weight: 300` 的写法会渲染出极细的字形；
* 平台的排版体系只用 400–700，因此把范围收紧到 400–900，
  让任何低于 400 的请求都落到 400，避免出现"意外很细"的标题。

## 更新流程

1. 用上面的命令重新生成子集（字符集变化时先重跑 `collect_glyphs.py`）；
2. 更新本文件里的 SHA-256 前 16 位；
3. 跑 `npm run typecheck && npm run build`，并确认页面无 `font-display` 造成的布局跳动。
