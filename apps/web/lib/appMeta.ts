/**
 * 应用元信息**单一来源**。
 *
 * 为什么要有这个文件：页脚、报告与页面标题此前各自硬编码版本号
 * （出现过 v1.0.0 与 v0.2.0 并存，且与后端 `app_version` 不一致），
 * 使用者无法判断眼前这份界面/报告究竟是哪个版本产出的。
 *
 * 版本取值与后端 `src/core/config.py::app_version` 对齐：
 * 前端只做展示，后端才是配置真值；两者不一致时以发布说明为准。
 */

export const APP_NAME = "股票玄学多模型研究平台";

/** 与后端 `Settings.app_version` 保持一致（展示形态统一带 v）。 */
export const APP_VERSION = "v0.2.0";

/** 页脚左侧文案（所有页面共用）。 */
export const APP_FOOTER_LEFT = `${APP_NAME} ${APP_VERSION}`;

/** 页脚右侧固定题词来源（避免各页各写一句）。 */
export const APP_FOOTER_CENTER = "让东方智慧与现代科学，在资本市场中相遇";
export const APP_FOOTER_RIGHT = "“道生一，一生二，二生三，三生万物。” ——《道德经》";
