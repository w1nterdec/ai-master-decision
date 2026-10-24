# 部署到持续运行的服务器

适合个人使用：云服务器运行应用，手机通过 `https://你的域名` 登录。电脑关机不影响服务器。手机与桌面共用同一应用和服务器数据。

当前没有按用户隔离的账户系统；这里的 HTTP Basic 登录只限制入口，所有知道密码的人共用同一份档案。只运行一个应用副本。SQLite 和 JSON 档案仍适用于个人、低频写入，不提供多人协作保证。

## 1. 准备服务器和域名

- 一台持续运行的 Ubuntu 24.04 LTS 云服务器，个人使用可从 2 核、2 GB 内存起步；这是起步配置建议，没有做并发容量测试。
- 一个域名或子域名，例如 `decision.example.com`。在 DNS 添加 A 记录指向服务器公网 IPv4；如果没有可用 IPv6，不要添加 AAAA 记录。
- 在云安全组允许 TCP 80、443；SSH 22 尽量只允许自己的管理 IP。应用的 8501 端口无需放行。
- 服务器安装 Git、Docker Engine 和 Compose 插件。按 [Docker 官方 Ubuntu 安装说明](https://docs.docker.com/engine/install/ubuntu/) 操作，确保当前用户能执行下列 Docker 命令。

国内服务器使用域名提供公网服务时，先核对云厂商的备案要求。域名、服务器和持续运行费用由云厂商收取，本项目不包含托管服务。

```bash
docker --version
docker compose version
sudo systemctl enable --now docker
```

默认使用 Caddy 直接接收公网 HTTPS。DNS、80/443 端口都要可达，且不能被其他服务占用；先不要叠加 CDN 或另一层代理。

## 2. 下载和配置

SSH 登录服务器后执行：

```bash
mkdir -p ~/apps
cd ~/apps
git clone https://github.com/w1nterdec/ai-master-decision.git
cd ai-master-decision
cp deploy/server.env.example .env
chmod 600 .env
docker run --rm -it caddy:2.10-alpine caddy hash-password
```

最后一条命令会交互式询问新密码；请使用长且独立的密码。复制生成的完整 bcrypt 哈希，然后编辑 `.env`：

```bash
nano .env
```

把 `APP_DOMAIN` 改为自己的真实域名（不带 `https://`、端口或路径），设置登录用户名，并把完整哈希填在 `BASIC_AUTH_PASSWORD_HASH` 的单引号内。保留哈希中的所有 `$`。不要填写明文密码，不要提交 `.env`，不要对外粘贴 `docker compose config` 的完整展开结果。

## 3. 启动

```bash
docker compose -f compose.server.yaml config --quiet
docker compose -f compose.server.yaml up --build -d
docker compose -f compose.server.yaml ps
docker compose -f compose.server.yaml logs --tail=80 app caddy
```

使用 `compose.server.yaml` 单独启动，不要与默认 `compose.yaml` 叠加；默认文件服务于电脑本地访问。密码配置为空时，服务器配置会拒绝启动。

Caddy 自动申请并续期 HTTPS 证书，反向代理支持 Streamlit 的 WebSocket。应用没有发布宿主机端口，只能从容器网络经登录入口访问。Caddy 必须是对外唯一入口。

初次构建需要下载镜像和 Python 依赖；服务器需能访问 GitHub、容器镜像仓库和 Python 包源。应用启动会从已入库历史研究初始化数据库，不会自动联网抓取招生数据。

手机打开 `https://你的域名`，输入上面设置的用户名和**原始密码**，不是哈希。可以使用浏览器“添加到主屏幕”，它仍是网页，需要网络连接。

## 4. 验收

```bash
# 不登录应返回 401，不能直接看到档案。
curl -I https://你的域名
# 交互式输入密码，登录后应返回 200。
curl -u owner -I https://你的域名
# 把 owner 换成 .env 中的用户名。真实页面渲染检查：
docker compose -f compose.server.yaml exec -T app python scripts/smoke_app.py
```

再在手机上切换页面、展开侧栏、筛选资料、保存一条测试备注并刷新确认。HTTP 200 只能证明 HTTP 请求通过，页面操作还需验证 WebSocket。确认云安全组没有开放 8501；Compose 的 app 服务也没有 `ports`。

## 5. 数据、更新与备份

数据库和个人档案放在 `decision-state` 命名卷的 `/state`，HTTPS 证书和 Caddy 状态在另外两个命名卷。`restart: unless-stopped` 配合 Docker 开机启动，使服务器重启后容器自动启动；手动停止的容器需要手动启动。配置本身不能保证云服务永不故障。

升级前备份。在仓库目录按顺序执行，备份期间暂停写入；`run` 覆盖应用启动命令，只归档数据卷，不重新导入：

```bash
mkdir -p backups
chmod 700 backups
docker compose -f compose.server.yaml stop app
docker compose -f compose.server.yaml run --rm --no-deps -T app tar -C /state -czf - . > backups/state.tgz
tar -tzf backups/state.tgz
chmod 600 backups/state.tgz
docker compose -f compose.server.yaml start app
```

确认备份命令成功、归档中有 `decision.db` 和已保存的 `decision_profile.json`；首次没有保存个人档案时可没有 JSON。示例文件名固定，下一次备份前改成新的日期文件名，以免覆盖旧备份。将备份加密后另存到服务器之外，定期演练恢复。`backups/` 已被 Git 和镜像构建忽略。

升级：

```bash
git pull --ff-only origin main
docker compose -f compose.server.yaml config --quiet
docker compose -f compose.server.yaml up --build -d
docker compose -f compose.server.yaml ps
```

数据卷会保留，但这不代替备份。不要执行 `docker compose down -v`，它会删除数据卷和证书状态。这个服务器部署使用独立的 Compose 项目名 `ai-master-decision-server`，不会自动读取电脑端数据库或默认本地 Compose 的卷。

迁移电脑数据或灾难恢复时，先停止 app，再把**匹配的完整状态目录**恢复到 `/state`：

```bash
docker compose -f compose.server.yaml stop app
docker compose -f compose.server.yaml run --rm --no-deps -u 0 -T app sh -c 'tar -C /state -xzf - && chown -R appuser:appuser /state' < backups/state.tgz
docker compose -f compose.server.yaml up -d app
```

恢复会覆盖同名文件；只使用自己的可信备份，并先备份现有状态。电脑端先停止原服务，归档数据库所在目录；若数据库和档案在不同目录，先复制到一个临时目录，命名为 `decision.db`、`decision_profile.json` 后打包，数据库存在 WAL 等伴随文件时也应一起保留。把归档安全传到服务器后按上面恢复。需要恢复到空状态卷时使用新项目/新卷，避免把两个状态目录混在一起。

## 常见问题

- **证书申请失败**：核对 A/AAAA 记录、云安全组和服务器防火墙的 TCP 80/443，再看 `caddy` 日志。域名应直接指向这台服务器。
- **502 或持续连接中**：看 app 健康状态和日志；确认服务名是 `app:8501`。不要关闭 Streamlit CORS/XSRF 来绕过故障。
- **换密码或域名**：改 `.env` 后重新执行 `docker compose -f compose.server.yaml up -d`，让环境配置重建容器；仅 `restart` 不应用新的环境变量。
- **登录弹窗没有“退出”按钮**：这是浏览器的 HTTP Basic 认证。关闭相关浏览器会话或使用无痕窗口；它不是应用内账户和会话管理。
- **多人看到同一档案**：当前设计如此。多人独立使用需要账户、按用户存储及权限隔离，进一步再评估 PostgreSQL。
- **没有域名**：先使用服务器上的 SSH 隧道或可信私有网络接入；本文自动 HTTPS 方案以域名为前提，不建议把无认证的 8501 端口直接发布到公网。
