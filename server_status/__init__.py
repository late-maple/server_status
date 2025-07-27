from mcdreforged.api.all import *
import time
import psutil
import requests
import json
import os



# 初始化服务器启动时间
def init_server_startup_time():
    try:
        # 获取当前进程的启动时间
        process = psutil.Process(os.getpid())
        return process.create_time()
    except Exception as e:
        # 如果无法获取进程启动时间，则使用当前时间
        return time.time()

# 保存服务器启动时间到文件
def save_server_startup_time_to_file(startup_time):
    try:
        server_dir = os.path.join('config', 'server_status')
        os.makedirs(server_dir, exist_ok=True)
        startup_time_file = os.path.join(server_dir, 'startup_time.json')
        with open(startup_time_file, 'w') as f:
            json.dump({"startup_time": startup_time, "pid": os.getpid()}, f)
    except Exception as e:
        pass  # 忽略保存错误

# 从文件加载服务器启动时间
def load_server_startup_time_from_file():
    try:
        startup_time_file = os.path.join('config', 'server_status', 'startup_time.json')
        if os.path.exists(startup_time_file):
            with open(startup_time_file, 'r') as f:
                data = json.load(f)
                saved_pid = data.get("pid")
                # 如果PID匹配，说明是插件重载而不是服务器重启
                if saved_pid == os.getpid():
                    return data.get("startup_time", time.time())
                else:
                    # PID不匹配，说明服务器已重启，创建新的启动时间
                    startup_time = init_server_startup_time()
                    save_server_startup_time_to_file(startup_time)
                    return startup_time
        else:
            # 如果文件不存在，创建新的启动时间记录
            startup_time = init_server_startup_time()
            save_server_startup_time_to_file(startup_time)
            return startup_time
    except Exception as e:
        # 出现错误时使用当前时间
        startup_time = init_server_startup_time()
        save_server_startup_time_to_file(startup_time)
        return startup_time

# 获取服务器启动时间
def get_server_startup_time():
    global server_startup_time
    return server_startup_time

# 在模块加载时初始化服务器启动时间
server_startup_time = load_server_startup_time_from_file()

startup_time = time.time()

DEFAULT_CONFIG = {
    "server_name": "Minecraft Server",
    "web_server_url": "http://localhost:5000/api/server_status",
    "server_id": "server_1",
    "report_interval": 60,
    "bot_prefixes": ["假的bot", "假的Bot_"]  # 支持多个前缀
}

config = None
# 添加一个标志来控制报告线程
reporting = False

def on_load(server: PluginServerInterface, prev_module):
    global startup_time, config
    config = server.load_config_simple('config.json', default_config=DEFAULT_CONFIG)
    startup_time = time.time()
    server.logger.info('服务器状态插件已加载')
    server.logger.info(f'服务器名称: {config["server_name"]}')
    server.register_command(
        Literal('!!status')
        .runs(lambda src: on_status_command(src))
        .then(
            Literal('connect')
            .requires(lambda src: src.has_permission(2))
            .runs(lambda src: test_connection(src))
        )
        .then(
            Literal('bots')
            .requires(lambda src: src.has_permission(2))
            .runs(lambda src: show_bots(src))
        )
    )
    server.register_help_message('!!status', '查看服务器运行时间和在线玩家数量')
    server.register_help_message('!!status connect', '测试与后端服务器的连接')
    server.register_help_message('!!status bots', '查看在线的假人玩家列表')

    # 启动定期报告状态的线程
    start_reporting(server)
    
    # 自动连接后端服务器并发送初始状态
    auto_connect_to_backend(server)


def on_unload(server: PluginServerInterface):
    global reporting
    reporting = False
    server.logger.info("服务器状态插件已卸载")


@new_thread("ServerStatus-AutoConnect")
def auto_connect_to_backend(server: PluginServerInterface):
    """插件启动后自动连接后端服务器"""
    server.logger.info("正在自动连接到后端服务器...")
    
    try:
        # 先发送连接通知
        connect_data = {
            "server_id": config["server_id"],
            "server_name": config["server_name"],
            "action": "connect"
        }
        
        response = requests.post(
            config["web_server_url"],
            json=connect_data,
            timeout=10
        )
        
        if response.status_code == 200:
            server.logger.info("成功连接到后端服务器")
        else:
            server.logger.warning(f"连接后端服务器时出现问题，状态码: {response.status_code}")
            
        # 立即发送一次完整状态
        time.sleep(2)  # 等待2秒确保连接建立
        send_full_status_update(server)
        
    except requests.exceptions.Timeout:
        server.logger.warning("连接后端服务器超时")
    except requests.exceptions.ConnectionError:
        server.logger.warning("无法连接到后端服务器")
    except Exception as e:
        server.logger.warning(f"连接后端服务器时发生未知错误: {str(e)}")


def send_full_status_update(server: PluginServerInterface):
    """立即发送一次完整的服务器状态"""
    try:
        status_data = build_status_data(server)
        response = requests.post(
            config["web_server_url"],
            json=status_data,
            timeout=10
        )
        
        if response.status_code == 200:
            server.logger.info("成功发送初始服务器状态")
        else:
            server.logger.warning(f"发送初始服务器状态时出现问题，状态码: {response.status_code}")
    except Exception as e:
        server.logger.warning(f"发送初始服务器状态时出现错误: {e}")


@new_thread("ServerStatus-Query") 
def on_status_command(src: CommandSource):
    src.reply(get_server_info(src.get_server()))


@new_thread("ServerStatus-Bots")
def show_bots(src: CommandSource):
    """显示假人玩家列表"""
    player_list = get_filtered_player_list()
    bots = player_list["bots"]
    
    if bots:
        src.reply(f"§7======= §6假人玩家列表 §7=======")
        for bot in bots:
            src.reply(f"§7- §6{bot}")
        src.reply(f"§7=========================")
    else:
        src.reply("§7当前没有在线的假人玩家")


@new_thread("ServerStatus-TestConnection")
def test_connection(src: CommandSource):
    """测试与后端服务器的连接"""
    src.reply(f"§7[§6ServerStatus§7] 正在测试与后端服务器的连接...")
    
    try:
        # 发送一个测试请求到配置的URL
        test_data = {
            "server_id": config["server_id"],
            "test_connection": True
        }
        
        response = requests.post(
            config["web_server_url"],
            json=test_data,
            timeout=10
        )
        
        if response.status_code == 200:
            src.reply(f"§7[§a成功§7] 成功连接到后端服务器!")
            src.reply(f"§7后端地址: §6{config['web_server_url']}")
            src.reply(f"§7响应状态: §6{response.status_code}")
        else:
            src.reply(f"§7[§c失败§7] 后端服务器返回错误状态码: {response.status_code}")
            
    except requests.exceptions.Timeout:
        src.reply(f"§7[§c失败§7] 连接超时，请检查后端服务器地址是否正确且可访问")
        src.reply(f"§7后端地址: §6{config['web_server_url']}")
        
    except requests.exceptions.ConnectionError:
        src.reply(f"§7[§c失败§7] 无法连接到后端服务器，请检查网络连接和服务器地址")
        src.reply(f"§7后端地址: §6{config['web_server_url']}")
        
    except Exception as e:
        src.reply(f"§7[§c失败§7] 测试连接时发生未知错误: {str(e)}")


@new_thread("ServerStatus-Reporter")
def start_reporting(server: PluginServerInterface):
    """启动定期报告服务器状态的线程"""
    global reporting
    reporting = True
    
    # 等待服务器完全启动
    time.sleep(5)
    
    # 立即发送一次状态更新
    try:
        status_data = build_status_data(server)
        response = requests.post(
            config["web_server_url"],
            json=status_data,
            timeout=10
        )
        
        if response.status_code != 200:
            server.logger.warning(f"发送初始服务器状态时出现问题，状态码: {response.status_code}")
    except Exception as e:
        server.logger.warning(f"发送初始服务器状态时出现错误: {e}")
    
    while reporting:
        try:
            # 构造服务器状态数据
            status_data = build_status_data(server)
            
            # 发送数据到后端服务器
            response = requests.post(
                config["web_server_url"],
                json=status_data,
                timeout=10
            )
            
            if response.status_code != 200:
                server.logger.warning(f"发送服务器状态时出现问题，状态码: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            server.logger.warning(f"发送服务器状态时出现网络错误: {e}")
        except Exception as e:
            server.logger.warning(f"发送服务器状态时出现未知错误: {e}")
            
        # 等待指定的时间间隔
        for _ in range(config["report_interval"]):
            if not reporting:
                return
            time.sleep(1)


def get_filtered_player_list():
    """获取过滤后的玩家列表，分离真实玩家和假人"""
    import minecraft_data_api as api
    try:
        amount, limit, players = api.get_server_player_list()
        if players is None:
            players = []
            
        # 分离真实玩家和假人
        real_players = []
        bots = []
        # 支持多个前缀
        bot_prefixes = config.get("bot_prefixes", ["假的bot"])
        
        for player in players:
            is_bot = False
            for prefix in bot_prefixes:
                if player.startswith(prefix):
                    bots.append(player)
                    is_bot = True
                    break
            if not is_bot:
                real_players.append(player)
                
        return {
            "real_players": real_players,
            "bots": bots,
            "real_amount": len(real_players),
            "bots_amount": len(bots),
            "total_amount": amount
        }
    except Exception as e:
        return {
            "real_players": ["获取失败"],
            "bots": [],
            "real_amount": 0,
            "bots_amount": 0,
            "total_amount": 0
        }


def build_status_data(server: PluginServerInterface) -> dict:
    """构建服务器状态数据"""
    def get_memory_used():
        return psutil.virtual_memory().percent
    
    def get_uptime():
        # 使用保存的服务器启动时间计算运行时间
        return int(time.time() - get_server_startup_time())
    
    player_info = get_filtered_player_list()
    
    # 构造要发送的数据
    status_data = {
        "server_id": config["server_id"],
        "server_name": config["server_name"],
        "uptime": get_uptime(),
        "memory_usage": get_memory_used(),
        "players": player_info["real_players"],  # 只发送真实玩家
        "bots": player_info["bots"],  # 单独发送假人玩家列表
        "player_count": player_info["real_amount"],  # 只计算真实玩家数量
        "bot_count": player_info["bots_amount"],  # 单独统计假人数量
        "last_update": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    }
    
    return status_data


def get_server_info(server: PluginServerInterface) -> RTextList:
    
    def get_menmory_used():
        return f"{psutil.virtual_memory().percent}"
    
    def get_uptime():
        # 使用服务器进程的启动时间计算运行时间
        uptime_seconds = int(time.time() - get_server_startup_time())
        hours = uptime_seconds // 3600
        minutes = (uptime_seconds % 3600) // 60
        seconds = uptime_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    player_list = get_filtered_player_list()
    real_players = player_list["real_players"]
    real_player_count = player_list["real_amount"]
    bot_count = player_list["bots_amount"]

    return RTextList(
        f"§7============ §6服务器状态 §7============\n",
        f"§6服务器运行时间§7: {get_uptime()}\n",
        f"§6内存使用率§7: {get_menmory_used()}%\n",
        f"§6真实玩家列表§7: {real_players}\n",
        f"§6真实玩家数量§7: {real_player_count}\n",
        f"§6假人玩家数量§7: {bot_count} (使用 !!status bots 查看)\n",
        f"§7==================================="
    )