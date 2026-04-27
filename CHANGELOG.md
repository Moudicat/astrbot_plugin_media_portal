# 更新日志

## [0.4.0] - 2026-04-27

### 新增 - 智能能力套件（可选）
- **TOTP 双因素登录**：基于 `pyotp` + `qrcode`，支持 Google Authenticator / 1Password / Bitwarden 等；
  - 新增 `/api/totp/*` 路由（绑定、校验、停用、恢复码再生），WebUI「设置 → 账号安全 · TOTP」分区可视化操作；
  - 一次性恢复码（8 个，bcrypt 哈希存盘），登录页支持 `挑战 token + 6 位动态码 / 恢复码` 双步验证；
  - 状态文件 `data/plugin_data/.../.totp_state` 单独落盘（权限 0o600），不进 SQLite、不进备份归档；
  - 配置项：`webui.totp_enabled` / `totp_issuer` / `totp_account`，依赖 `requirements-totp.txt`。
- **CLIP 语义检索（Chinese-CLIP ViT-B/16, ONNX）**：
  - 全新 `core/intelligence/clip/` 子系统：`engine`（ONNX Runtime 推理）/ `preprocess`（中文 CLIP 预处理）/ `tokenize`（中文分词）/ `index`（SQLite 向量库）/ `worker`（后台批量索引）；
  - REST API：`/api/intelligence/status` / `clip/scan` / `clip/search` 等；
  - 新增 LLM 工具 `search_media_semantic(query, limit, category)`，仅在模型就绪时注册到 LLM；
  - 依赖 `requirements-clip.txt`（onnxruntime + tokenizers + Pillow + numpy）。
- **人脸检测 / 识别 / 聚类（InsightFace `buffalo_s`, ONNX）**：
  - 全新 `core/intelligence/face/` 子系统：`engine`（RetinaFace + ArcFace 推理）/ `index`（人脸 / 人物 / 缩略图 SQLite 库）/ `cluster`（在线增量分配 + 周期性 DBSCAN 全量聚类）/ `worker`（后台扫描）；
  - REST API：人物列表 / 详情 / 改名 / 删除 / 合并 / 拆分 / 重新聚类 / 人脸缩略图直链；
  - WebUI 新增「人脸」一级菜单（`FacesView`、`FacePersonDrawer`），支持批量合并、单人物拆分、改名等可视化操作；
  - 新增 LLM 工具 `list_face_persons(limit)` / `find_media_with_person(person, limit)`；
  - 依赖 `requirements-face.txt`（insightface + scikit-learn + opencv-python-headless）。
- **统一模型管理**：
  - `core/intelligence/manager.py` 中 `IntelligenceManager` 统一管理 CLIP / Face 生命周期、模型下载、依赖检测、后台 worker；
  - `ModelDownloader` 支持断点续传、SHA256 校验、`hf_mirror_url` 自动重写、并发下载上限；
  - 新增 `intelligence` 配置分组：`enabled` / `clip_enabled` / `face_enabled` / `hf_mirror_url` / `max_concurrent_downloads`；
  - 模型与索引文件落在 `data/plugin_data/.../intelligence/`。

### 新增 - 调试与开发体验
- `scripts/debug_webui.py` 新增 `--totp` / `--no-totp` / `--totp-issuer` / `--totp-account`，本地调试默认开启 TOTP；
- 后台设置面板加宽（`SettingsDialog.vue`），适配新增的 TOTP / 智能能力分区。

### 测试
- 新增 `test_totp_store.py` / `test_webui_totp_login.py` / `test_intelligence_models.py` / `test_clip_engine.py` / `test_clip_index.py` / `test_face_index.py` / `test_face_worker.py` / `test_webui_intelligence_routes.py`，新增覆盖约 50+ 用例；
- 全套测试 160 通过 / 1 跳过。

### 文档
- `docs/rfc-2026-04-intelligence-suite.md`：完整 RFC（设计 + 数据流 + schema + 安全考量）；
- README 新增「🧠 智能能力（可选）」章节、配置说明 `intelligence` 与新 LLM 工具列表。

## [0.3.1] - 2026-04-21

### 新增
- 支持回收站全流程：软删除、恢复、单条彻底删除、过期自动/手动清理、保留天数设置
- 支持 SHA256 重复检测
- 新增重复视图与回收站页面，侧栏新增回收站快捷入口
- 支持缩略图衍生资源自动生成与缓存管理
- 支持多语言（zh-CN / en-US / ja-JP）

### 优化
- 分类切换支持 URL query 持久化，刷新后保持当前分类
- 列表模式 UI 优化

## [0.3.0] - 2026-04-20

### 新增
- **前端开发工作流重构**
- **拖拽 / 粘贴上传**：支持将文件拖进窗口或粘贴剪贴板图片直接进入上传队列
- **媒体列表视图切换**：卡片 / 列表两种形式一键切换
- **Settings 扩展**：
  - 主题色切换
  - 默认页大小、网格密度
  - 本地 UI 偏好导出 / 导入（JSON）
- **备份 / 恢复**：新增 `/api/backup/export` 与 `/api/backup/import`，打包导出 `tar.gz`（DB + categories.json + 媒体目录），支持仅元数据或含媒体两种模式，导入时可选替换媒体目录

### 优化
- 详情抽屉改为「内容滚动 + 底部操作条常驻」布局，保存后自动关闭
- 卡片模式下音频 / 其它文件占位符修复长文件名挤走图标的问题

## [0.2.2] - 2026-04-20

### 新增
- WebUI 新增 **PC 端右键菜单**：
  - 分类右键支持**改名**与**删除**，默认分类不可修改；
  - 「全部媒体」右键显示「无法修改」占位项；
  - 媒体右键提供**复制链接 / 保存 / 在新窗口打开 / 删除**。
- 首页顶部 **统计卡片支持逐项开关**
- 静态资源新增 **版本指纹**

### 优化
- CSS样式调整
- **大图 / 视频预览**支持点击空白区域关闭

## [0.2.1] - 2026-04-19

### 新增
- `update_media` / `tool_update_media` 新增 `filename` 参数，支持在保持分类与描述不变的前提下重命名媒体文件
- 媒体库新增 `duration` 字段
- `/media list`、`/media search`、`list_media_in_category`、`search_media` 附带 **大小 / 上传时间**，音频与视频额外附带 **时长**
- WebUI支持修改文件名
- 底部音频条新增最小化按钮

### 优化
- 修复 WebUI 媒体详情抽屉与底部音频条的遮挡问题

### 兼容性
- 新增软依赖 `mutagen>=1.47`（音频 / MP4 视频时长探测）

## [0.2.0] - 2026-04-19

### 新增
- WebUI 批量操作条滚动置顶

### 修复
- 安全性修复

### 优化
- WebUI 优化

## [0.1.3] - 2026-04-18

### 修复
- 安全性修复

### 优化
- WebUI 访问地址识别优化：自动过滤疑似 Docker 网桥 IP（如 `172.17.x.x`、`172.18.x.x`），不再把容器内部地址混在可访问地址列表中；检测到容器环境（Docker/K8s 等）且未配置 `webui.public_base_url` 时，会在 `/media webui` 回执与启动日志中提示建议设置公开访问地址
- WebUI 新增 Header「设置」入口，内含**分类管理**（重命名、修改描述、删除）与**清理空分类**两大操作
- WebUI 选中媒体后新增「批量分类」按钮，可把多个媒体一次性移动到已有或新建的分类

## [0.1.2] - 2026-04-18

### 新增
- 新增 LLM 工具 `move_media(media_ids, category)` —— 支持批量媒体重分类，目标分类不存在会自动创建；人工操作仍推荐走 WebUI。
- 新增 LLM 工具 `update_media(media_id, category, description, tags)` —— 统一更新媒体的分类 / 描述 / 标签，`tags` 传 `-` 即清空。

### 修复
- 修复 `get_media_url` LLM 工具的参数文档缺失，部分 LLM 无法正确传入 `media_id` 的问题；兼容字符串形式的 media_id 入参。
- 修复 `send_media` 在 WebChat 聊天界面出现裂图的情况

### 优化
- `/media list` 调整默认条目上限为 10，并在输出末尾显示总数与扩展参数提示；避免一次性吐出全部媒体。
- 删除与 `/media webui` 功能重复的 `/media password` 子命令，密码可直接在 WebUI 设置页或插件配置中维护。
- `/media categories` 与 `list_media_categories` 工具输出的分类体积改为人类可读格式（如 `48.9MB`），不再显示裸 `B` 字节数。

## [0.1.1] - 2026-04-18

### 新增
- 新增亮色 / 暗色主题切换，自动记住偏好。
- 支持独立调试 WebUI（无需启动 AstrBot 主程序），方便本地开发预览。
- 上传进度条、类目快速创建、数据目录文件预览等更顺手的小功能。

### 优化
- 登录态会自动保持，直到过期或服务端重启
- **移动端体验大幅改进**：
  - 统计栏改为紧凑的横向文字样式，不再挤占屏幕。
  - 搜索框和上传按钮同排显示，新增明显的"搜索 / 清空"按钮，更易点按。
  - 媒体缩略图右上角的操作按钮放大到舒适的点击尺寸。
  - 媒体详情弹窗中的图片完整显示、不再被裁切；底部按钮从四个竖排合并为两行布局，少占空间。
  - 去除点按按钮/链接时残留的灰蓝色高亮

### 修复
- 解决了部分按钮长按时会弹出系统菜单或错误选中文本的问题。

## [0.1.0] - 2026-04-17

### 新增
- 首个正式版发布 🎉
- 多媒体保存、检索、发送与可视化管理。
- WebUI 控制台：支持上传、搜索、按类目筛选。
- 支持 AI 直接调用（Tool Call），让机器人能自主管理多媒体资源。
