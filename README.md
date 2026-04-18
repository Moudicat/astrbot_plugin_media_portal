<div align="center">

<img src="./logo.png" alt="Astrbot Media Portal" width="160" />

# 🌌 Astrbot Media Portal

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)
[![Repo](https://img.shields.io/badge/GitHub-Moudicat%2Fastrbot__plugin__media__portal-black)](https://github.com/Moudicat/astrbot_plugin_media_portal)

[![Moe Counter](https://count.getloli.com/get/@astrbot_plugin_media_portal?theme=moebooru)](https://github.com/moudicat/astrbot_plugin_media_portal)

</div>

一个面向 **AI + 人工协作** 的 AstrBot 多媒体管理插件。  
目标是让 AI 具备「保存 / 查询 / 搜索 / 发送媒体」能力，同时给你一个可视化 Web 控制台统一管理媒体资产。

## 📑 目录

- [🌌 Astrbot Media Portal](#-astrbot-media-portal)
  - [📑 目录](#-目录)
  - [🚀 功能特点](#-功能特点)
  - [📦 安装方式](#-安装方式)
  - [🛠️ 快速开始](#️-快速开始)
  - [🤖 LLM 工具列表](#-llm-工具列表)
  - [🧰 命令列表](#-命令列表)
  - [⚙️ 配置说明](#️-配置说明)
  - [🖥️ WebUI 说明](#️-webui-说明)
  - [❓ 常见问题](#-常见问题)
  - [🔒 安全建议](#-安全建议)
  - [🧪 独立调试 WebUI](#-独立调试-webui)
  - [📚 开发参考](#-开发参考)

## 🚀 功能特点

| 功能 | 描述 |
| --- | --- |
| 🤖 AI 可调用媒体工具 | 支持保存媒体、列出分类、按分类列媒体、关键词搜索、获取 URL、直接发送媒体 |
| 📁 多来源入库 | 支持消息附件、URL 下载、本地路径（move/copy）保存 |
| 🗂️ 分类管理 | 分类描述、分类重命名、分类删除、目录扫描回填索引 |
| 🌐 Web 控制台 | 密码登录、Token 会话、媒体 CRUD、URL 保存、批量删除 |
| 🎬 多媒体预览 | 图片查看、视频播放、音频播放（含底部常驻音频播放器） |
| 📱 响应式 | 同时适配 PC 与移动端 |
| 🔍 Data 资源浏览 | 只读浏览 AstrBot `/data` 目录，支持图片/视频/音频预览 |
| 🔐 安全控制 | 登录限流、媒体只读 token、路径越界防护、体积限制 |

## 🖼️ 截图

<details>
<summary><strong>后台管理界面</strong></summary>
<br />
<img width="1274" height="981" alt="085251bc35b6c5aa4d7c2304d81839e6" src="https://github.com/user-attachments/assets/a9184815-114b-458b-be5c-8cb32c634e95" />
</details>

<details>
<summary><strong>添加媒体文件进媒体库</strong></summary>
<br />
<img width="735" height="90" alt="image" src="https://github.com/user-attachments/assets/9d952ca5-f216-4491-aed1-4158bf87f259" />
<br />
<img width="904" height="535" alt="image" src="https://github.com/user-attachments/assets/f4d2faef-6b78-4cb2-9d37-212b56a77c1d" />
</details>

<details>
<summary><strong>从媒体库读取/发送</strong></summary>
<br />
<img width="1200" height="1246" alt="136aeefd05caa91b52ebb7b2fb34f560" src="https://github.com/user-attachments/assets/58243bc1-db22-4603-a3e6-32df5f23cddd" />
</details>

## 📦 安装方式

1. 将插件放入 AstrBot 插件目录；
2. 安装依赖：

```bash
pip install -r requirements.txt
```

3. 重启 AstrBot 或热重载插件。

## 🛠️ 快速开始

1. 在 AstrBot 后台启用插件；
2. 管理员执行：
   - `/media webui`
3. 复制返回地址，在浏览器打开后输入密码登录；
4. 使用上传/URL 保存功能入库媒体；
5. 在对话中让 AI 调用 `save_media`、`search_media`、`send_media` 等工具。

## 🤖 LLM 工具列表

### `save_media(source, category, description, filename, move)`

- `source=""`：从当前消息提取附件；
- `source` 为 `http/https`：下载后保存；
- `source` 为本地路径：直接入库；
- `move=true`：本地路径默认移动（`mv` 语义）；
- `move=false`：改为拷贝。

### 其他工具

- `list_media_categories()`
- `list_media_in_category(category, limit, kind)`
- `search_media(query, limit, category)`
- `get_media_url(media_id)`  
  返回 WebUI 暴露 URL，生成优先级：`webui.public_base_url` > `callback_api_base` > 自动 `host:port`。
- `send_media(media_id_or_query)`  
  支持传 ID 或关键词，工具内部直接向当前会话发送媒体。
- `move_media(media_ids, category)`  
  将一个或多个媒体重分类到目标分类，`media_ids` 支持单值或逗号分隔（如 `"12,15"`），目标分类不存在会自动创建。
- `update_media(media_id, category, description, tags)`  
  统一更新媒体的分类 / 描述 / 标签，留空字段即不修改；`tags` 传 `"-"` 表示清空标签。

## 🧰 命令列表

命令组：`/media`

| 指令 | 说明 |
| --- | --- |
| `/media webui` | 查看 WebUI 地址与密码（管理员） |
| `/media categories` | 查看分类及统计 |
| `/media list [category] [limit] [kind]` | 列出媒体，默认最多 10 条，`limit` 最高 50 |
| `/media search <query> [limit] [category]` | 搜索媒体 |
| `/media scan` | 扫描目录并修复索引（管理员） |

> 媒体的重分类 / 描述 / 标签调整建议在 WebUI 上完成，或让 AI 调用 `move_media` / `update_media` 工具。

> 密码修改可直接在 WebUI 设置页内完成，或修改 `webui.access_password` 配置后重载插件。

## ⚙️ 配置说明

配置文件：`_conf_schema.json`

### `webui`

- `enabled`：是否启用 WebUI；
- `host`：监听地址（默认 `0.0.0.0`）；
- `port`：监听端口（默认 `7003`）；
- `access_password`：访问密码（留空自动生成）；
- `session_timeout`：会话超时秒数；
- `public_base_url`：自定义外部访问地址（如反向代理域名）；
- `expose_astrbot_data`：是否开放 `/data` 只读浏览（默认 `false`）；
- `allowed_origins`：允许跨域来源白名单（留空不开放跨域）；
- `readonly_token_ttl`：WebUI 媒体预览 token 有效期（秒）；
- `share_url_ttl`：`get_media_url` / 复制链接生成 token 的有效期（秒）；
- `data_token_ttl`：Data 文件直链 token 有效期（秒）。

### `storage`

- `location_mode`：媒体库存储位置，可选：
  - `plugin_data`（**默认**）→ `data/plugin_data/astrbot_plugin_media_portal/media`，符合 AstrBot [官方插件规范](https://docs.astrbot.app/dev/star/plugin.html)，便于备份、迁移与卸载清理。
  - `astrbot_data` → `data/media`

#### 🚚 在两种模式间切换

SQLite 中保存的是相对媒体根目录的路径，**切换模式本身不需要改库**，只需要搬一次文件：

1. 停用插件或停机 AstrBot；
2. 将旧目录下的所有内容整体移动到新目录（例如 `data/media/*` → `data/plugin_data/astrbot_plugin_media_portal/media/`）；
3. 将 `storage.location_mode` 改为目标模式；
4. 重启插件；
5. 建议执行 `/media scan` 校验一次索引。

### `downloader`

- `max_file_size_mb`：单文件最大体积；
- `allowed_kinds`：允许类型（`image/video/audio`）；
- `default_move_local`：本地路径入库默认是否 `move`。

## 🖥️ WebUI 说明

### 页面能力

- 登录页：密码登录；
- 媒体页：分类筛选、关键词搜索、类型筛选、上传、URL 保存、详情编辑；
- **多选操作**：批量删除、批量移动到已有/新建分类；
- **顶栏「设置」**：分类管理（重命名、改描述、删除）、清理空分类；
- 预览层：图片查看、视频播放；
- 音频：底部常驻播放器；
- Data 浏览页：目录树浏览 AstrBot `/data`，支持只读预览与下载。

### 访问控制

- API 使用 Bearer Token；
- 媒体流使用带签名、带过期时间的只读 token；
- Data 文件访问使用独立 token（与媒体 token 分离）。

## ❓ 常见问题

### Q1：`get_media_url` 返回的地址为什么不是本机 IP？

A：优先级是 `public_base_url` > `callback_api_base` > 自动地址。  
如果你做了反代，建议明确配置 `public_base_url`。

### Q2：能不能让 Agent 先下载到本地，再调用 `save_media`？

A：可以。传本地文件路径给 `save_media` 即可，并通过 `move` 控制是移动还是拷贝。

### Q3：是否能浏览整个 AstrBot `/data`？

A：可以，只读模式。可通过 `webui.expose_astrbot_data` 控制开关。

### Q4：`/media webui` 列出来的 `172.x.x.x` 为什么访问不到？

A：那是容器（Docker / K8s）内部网桥地址，宿主机/外网本来就不可达。插件会自动识别常见的 Docker 网桥段（`172.17.0.0/12`），**默认从地址列表中过滤**，只展示 `localhost` 与真正的局域网 IP。

- 在容器里部署时，请在插件配置的 `webui.public_base_url` 中填写**宿主机可访问的地址**（例如 `http://192.168.1.10:7003`）或反代域名；
- 设置后，`get_media_url`、WebUI 分享链接、`/media webui` 回执都会基于该地址生成；
- 若检测到容器环境且未配置 `public_base_url`，`/media webui` 与启动日志会主动给出提示。

## 🔒 安全建议

1. 生产环境务必设置固定强密码，不要长期使用随机密码；
2. 若开放公网访问，请配合反向代理与 HTTPS；
3. 分享链接已带过期时间，但仍建议最小化转发范围并定期轮换密码；
4. 建议限制上传/下载来源并定期清理历史媒体。

## 🧪 独立调试 WebUI

不启动 AstrBot 主程序也可以单独跑 WebUI。仓库内提供了 `scripts/debug_webui.py`，它会在运行时注入 `astrbot.*` 的最小 shim 模块、手动装配 `MediaManager/CategoryManager`，然后启动完整 FastAPI 应用。

```bash
# 在插件根目录执行
pip install -r requirements.txt

# 默认 127.0.0.1:7003 / 密码 admin123 / 数据落在 ./.devdata/
python scripts/debug_webui.py

# 自定义端口 & 密码 & 开放局域网 & 开启 /data 只读浏览
python scripts/debug_webui.py --host 0.0.0.0 --port 8080 --password mypass --expose-data

# 开启 Python 代码热重载（需 pip install watchfiles）
python scripts/debug_webui.py --reload
```

关键点：

- **前端静态文件（`webui/static/`）热生效**：修改 `index.html` / `app.js` / `styles.css` / `components/*` 后，浏览器刷新即可看到新版本，无需重启服务；
- **Python 代码改动**：默认需要 `Ctrl+C` 后重跑；加 `--reload` 即可在 `core/` 与 `webui/` 变更时自动重启；
- **调试数据隔离**：默认落在插件根目录下 `./.devdata/`（已写入 `.gitignore`），可随时删除以复位；或用 `--data-dir` / `--astrbot-data` 指定其他位置；
- **不依赖 AstrBot 运行时**：脚本只提供 `logger` 占位等最小依赖，仅用于本地调试；生产仍请通过 AstrBot 正常加载插件。

常用参数：

| 参数 | 说明 |
| --- | --- |
| `--host` / `--port` | 监听地址 / 端口 |
| `--password` | 访问密码（默认 `admin123`，仅供本地） |
| `--data-dir` | 自定义插件数据根（放 `index.db` / `categories.json` / `media/`） |
| `--astrbot-data` | 模拟的 AstrBot `data/` 目录（配合 `--expose-data` 测试 Data 浏览） |
| `--expose-data` | 打开 `/api/data-*` 及 Data 页面（只读） |
| `--public-base-url` | 反代/公开域名，用于生成分享链接 |
| `--session-timeout` | 登录会话秒数（默认 86400，调试期偏长） |
| `--allowed-origins` | CORS 白名单（逗号分隔） |
| `--reload` | 启用 Python 代码热重载（依赖 watchfiles） |

## 📚 开发参考

- [AstrBot 最小实例](https://docs.astrbot.app/dev/star/guides/simple.html)
- [AstrBot 插件开发文档（中文）](https://docs.astrbot.app/dev/star/plugin-new.html)
- [AstrBot 插件开发指南（含消息组件/函数工具）](https://docs.astrbot.app/dev/star/plugin.html)
