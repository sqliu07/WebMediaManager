# MediaManager

MediaManager 是一个基于 Flask 构建的电影元数据管理和刮削工具，适用于本地 NAS 或视频收藏目录。它具备类似 TinyMediaManager 的 Web 界面，可以扫描目录中的影片文件，调用 TMDB API 获取电影信息，并自动生成 NFO 文件、海报、背景图等，用于 Jellyfin、Emby、Kodi 等媒体服务器。

## 功能特性

### 目录扫描
- 自动扫描指定路径下的视频文件
- 支持识别 mp4、mkv、mov、avi、flv 等格式
- 检测影片是否已有海报、NFO、背景图文件

### 刮削功能（TMDB）
- 支持通过影片名称和年份手动搜索 TMDB
- 刮削后自动下载海报（poster）、背景图（fanart）
- 自动生成 Jellyfin/TinyMediaManager 兼容的 NFO 元数据文件
- 文件组织格式：电影名 (年份)/电影名.年份.分辨率.扩展名

### 前端界面
- 左侧为影片列表，显示刮削状态
- 右侧为影片详细信息区，展示海报、简介、评分和演员表
- 支持点击影片查看详情或重新刮削

### 日志系统
- 使用 Python logging 输出到控制台和日志文件
- 日志文件保存在 log/ 目录，按时间戳命名
- .gitignore 默认忽略日志文件

## 项目结构

MediaManager/
├── app.py
├── scraper.py
├── nfo.py
├── logger.py
├── config.json
├── requirements.txt
├── templates/
│   └── index.html
├── static/
│   ├── app.js
│   └── style.css
└── log/

## 安装与配置

### 1. 安装依赖
pip install -r requirements.txt

### 2. 配置 TMDB API Key
编辑 config.json：
```
{
  "tmdb": {
    "api_key": "你的TMDB_API_KEY",
    "language": "zh-CN"
  },
  "scan": {
    "root_dir": "data"
  }
}
```

### 3. 运行程序
python app.py

访问地址：
http://127.0.0.1:8003

## 使用方法

### 扫描影片
1. 输入影片目录路径
2. 点击“扫描目录”，左侧显示影片文件
3. 可查看是否已有海报、NFO、背景图状态

### 手动刮削
1. 点击某部影片
2. 点击“手动搜索”
3. 输入电影名与年份
4. 选择结果后开始自动刮削
5. 刮削进度实时显示

### 文件生成结构
电影名 (年份)/
├── 电影名.年份.2160p.mkv
├── 电影名.年份.2160p.poster.jpg
├── 电影名.年份.2160p.fanart.jpg
└── 电影名.年份.2160p.nfo

## 日志系统说明

日志保存在 log/ 目录，格式为：
2025-10-18_21-30-05.log

日志内容示例：
2025-10-18 21:30:05 [INFO] 扫描目录: data/
2025-10-18 21:30:06 [INFO] [01] 哈利·波特与魔法石.2001.2160p.mkv | 海报=False NFO=False 背景=False

## 常见问题

Q: 搜索无结果？
A: 确认 TMDB API Key 是否正确，影片名称是否干净。

Q: 刮削完成后前端不显示？
A: 重新点击目录项查看，或检查日志文件定位原因。

Q: 如何修改命名规则？
A: 打开 scraper.py，编辑 scrape_one 函数中的文件命名逻辑。

## 开发计划
- 支持批量刮削
- 支持字幕下载接口
- 提供 Docker 部署
- 增加剧集刮削模式

## 许可证

本项目基于 MIT License 发布，允许任何人自由使用、修改、分发和用于商业用途，但必须保留原始版权声明。

详细内容请见 LICENSE 文件。
