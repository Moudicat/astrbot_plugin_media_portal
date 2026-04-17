# 🌌 AstrBot Media Portal

<div align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)
[![Repo](https://img.shields.io/badge/GitHub-Moudicat%2Fastrbot__plugin__media__portal-black)](https://github.com/Moudicat/astrbot_plugin_media_portal)

</div>

一个面向 **AI + 人工协作** 的 AstrBot 多媒体管理插件。  
目标是让 AI 具备「保存 / 查询 / 搜索 / 发送媒体」能力，同时给你一个可视化 Web 控制台统一管理媒体资产。

## 📑 目录

- [🌌 AstrBot Media Portal](#-astrbot-media-portal)
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

## 🧰 命令列表

命令组：`/media`

| 指令 | 说明 |
| --- | --- |
| `/media webui` | 查看 WebUI 地址与密码（管理员） |
| `/media password show` | 查看当前密码（管理员） |
| `/media password regen` | 重置随机密码（管理员） |
| `/media password set <password>` | 设置指定密码（管理员） |
| `/media categories` | 查看分类及统计 |
| `/media list [category] [limit] [kind]` | 列出媒体 |
| `/media search <query> [limit] [category]` | 搜索媒体 |
| `/media scan` | 扫描目录并修复索引（管理员） |

## ⚙️ 配置说明

配置文件：`_conf_schema.json`

### `webui`

- `enabled`：是否启用 WebUI；
- `host`：监听地址（默认 `0.0.0.0`）；
- `port`：监听端口（默认 `7003`）；
- `access_password`：访问密码（留空自动生成）；
- `session_timeout`：会话超时秒数；
- `public_base_url`：自定义外部访问地址（如反向代理域名）；
- `expose_astrbot_data`：是否开放 `/data` 只读浏览。

### `storage`

- `media_dir_override`：覆盖媒体目录，留空默认 `{astrbot_data}/media`。

### `downloader`

- `max_file_size_mb`：单文件最大体积；
- `allowed_kinds`：允许类型（`image/video/audio`）；
- `default_move_local`：本地路径入库默认是否 `move`。

## 🖥️ WebUI 说明

### 页面能力

- 登录页：密码登录；
- 媒体页：分类筛选、关键词搜索、类型筛选、上传、URL 保存、详情编辑；
- 预览层：图片查看、视频播放；
- 音频：底部常驻播放器；
- Data 浏览页：目录树浏览 AstrBot `/data`，支持只读预览与下载。

### 访问控制

- API 使用 Bearer Token；
- 媒体流使用只读 token（便于 `<img>/<video>/<audio>` 直接访问）。

## ❓ 常见问题

### Q1：`get_media_url` 返回的地址为什么不是本机 IP？

A：优先级是 `public_base_url` > `callback_api_base` > 自动地址。  
如果你做了反代，建议明确配置 `public_base_url`。

### Q2：能不能让 Agent 先下载到本地，再调用 `save_media`？

A：可以。传本地文件路径给 `save_media` 即可，并通过 `move` 控制是移动还是拷贝。

### Q3：是否能浏览整个 AstrBot `/data`？

A：可以，只读模式。可通过 `webui.expose_astrbot_data` 控制开关。

## 🔒 安全建议

1. 生产环境务必设置固定强密码，不要长期使用随机密码；
2. 若开放公网访问，请配合反向代理与 HTTPS；
3. 不要泄露 `get_media_url` 返回的只读 token 链接；
4. 建议限制上传/下载来源并定期清理历史媒体。

## 📚 开发参考

- [AstrBot 最小实例](https://docs.astrbot.app/dev/star/guides/simple.html)
- [AstrBot 插件开发文档（中文）](https://docs.astrbot.app/dev/star/plugin-new.html)
- [AstrBot 插件开发指南（含消息组件/函数工具）](https://docs.astrbot.app/dev/star/plugin.html)
