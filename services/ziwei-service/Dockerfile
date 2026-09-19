# 紫微排盘服务（Node.js + iztro）
#
# 多阶段构建：构建期需要 devDependencies（typescript），运行期只要 iztro + dist。
# 依赖使用 `npm ci`（锁定 package-lock.json），保证镜像可复现。

FROM node:22-alpine AS build
WORKDIR /svc

COPY package.json package-lock.json ./
RUN npm ci --no-fund --no-audit

COPY tsconfig.json ./
COPY src ./src
RUN npm run build

# --- 运行期 ---
FROM node:22-alpine AS runtime
WORKDIR /svc
ENV NODE_ENV=production

COPY package.json package-lock.json ./
RUN npm ci --omit=dev --no-fund --no-audit && npm cache clean --force

COPY --from=build /svc/dist ./dist

# 排盘服务不是对外接口：只在 compose 内部网络暴露
EXPOSE 8100
ENV ZIWEI_HOST=0.0.0.0
ENV ZIWEI_PORT=8100

USER node
CMD ["node", "dist/server.js"]
