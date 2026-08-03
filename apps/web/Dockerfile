# 生产前端镜像：直接用宿主机预构建的 dist/（npm run build 已在 CI/本地完成）
# 这样避免在容器内重跑 npm install（慢且依赖网络）。
FROM nginx:alpine
COPY dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ || exit 1
CMD ["nginx", "-g", "daemon off;"]
