# Server Status - MCDReforged 插件

<p align="center">
  <img src="https://img.shields.io/badge/MCDR-2.0%2B-blue" alt="MCDR Version">
  <img src="https://img.shields.io/badge/version-1.2.5-brightgreen" alt="Version">
  <img src="https://img.shields.io/github/license/Lazy-Bing-Server/Server-Status" alt="License">
</p>

> 一个功能强大的 MCDReforged 插件，用于监控 Minecraft 服务器状态，实时展示服务器运行时间、内存占用、在线玩家等关键信息。

## 🌟 功能亮点

- 🔧 **实时监控**: 实时获取服务器运行时间、内存使用情况
- 👥 **玩家统计**: 精确区分真实玩家与假人玩家
- 🌐 **Web 面板**: 直观的可视化界面展示服务器状态
- ⚙️ **多服务器支持**: 可同时监控多个服务器实例
- 📊 **详细数据**: 提供全面的服务器性能指标

## 📋 安装要求

- MCDReforged (MCDR) 2.0 或更高版本
- Python 3.7+
- Flask 和 Flask-CORS (用于 Web 面板)
- [minecraft_data_api](https://github.com/Fallen-Breath/MinecraftDataAPI) 插件

## 📦 安装方法

1. 下载插件文件
2. 将插件文件夹放入 MCDR 的 `plugins` 目录
3. 重启 MCDR 服务器加载插件

## ⚙️ 配置说明

首次运行插件会自动生成配置文件 `config/server_status/config.json`：

```json
{
  "server_name": "Minecraft Server",
  "web_server_url": "http://localhost:5000/api/server_status",
  "server_id": "server_1",
  "report_interval": 60,
  "bot_prefixes": ["假的bot", "假的Bot_"]
}
```

### 配置参数详解

- `server_name`: 服务器显示名称
- `web_server_url`: 后端服务器地址
- `server_id`: 服务器唯一标识符
- `report_interval`: 状态上报间隔(秒)
- `bot_prefixes`: 假人玩家前缀列表，用于区分真实玩家和假人

## 🎮 使用说明

### 命令列表

| 命令 | 权限等级 | 描述 |
|------|---------|------|
| `!!status` | 0 | 查看服务器运行时间和在线玩家数量 |
| `!!status test` | 2 | 测试与后端服务器的连接 |
| `!!status bots` | 2 | 查看在线的假人玩家列表 |

### 权限说明

- **等级 0**: 普通玩家可使用的命令
- **等级 2**: 管理员专用命令

## 🌐 Web 面板

插件包含一个 Web 面板用于可视化展示服务器状态信息。

### 启动 Web 服务

```bash
cd web_server
pip install flask flask-cors
python app.py
```

访问 `http://localhost:5000` 查看服务器状态面板。

### Nginx 反向代理配置

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location /status/ {
        proxy_pass http://localhost:5000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 🛠️ 技术特色

### 精确的运行时间计算

插件使用服务器进程启动时间而非插件加载时间来计算运行时间，确保即使插件重载也不会重置计时器。

### 智能玩家识别

通过配置的前缀列表自动区分真实玩家和假人玩家，并分别统计显示。

### 稳定的数据传输

采用 HTTP POST 请求定期向后端发送服务器状态，确保数据传输的可靠性。

## 🐛 故障排除

### 无法连接到后端服务器

1. 检查后端服务是否正在运行
2. 确认 `web_server_url` 配置是否正确
3. 检查网络连接和防火墙设置
4. 使用 `!!status test` 命令测试连接

### Web 面板无数据显示

1. 确认插件已正确加载并运行
2. 检查服务器是否能正常连接到后端
3. 查看后端服务日志确认是否收到数据

## 📄 许可证

本项目采用 MIT 许可证，详情请参见 [LICENSE](LICENSE) 文件。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request 来帮助改进这个插件！