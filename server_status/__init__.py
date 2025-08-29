from mcdreforged.api.all import *
import time
import psutil
import requests
import json
import os
import mysql.connector
from mysql.connector import Error
from threading import Lock



def init_server_startup_time():
    try:
        process = psutil.Process(os.getpid())
        return process.create_time()
    except Exception as e:
        return time.time()

MYSQL_CONFIG = {
    'host': 'localhost',
    'database': 'server_status',
    'user': 'server_status',
    'password': 'status',
    'charset': 'utf8mb4',
    'autocommit': True,
    'raise_on_warnings': False,
    'connection_timeout': 10
}

player_record_lock = Lock()

def get_mysql_connection(server: PluginServerInterface):
    try:
        connection = mysql.connector.connect(**MYSQL_CONFIG)
        return connection
    except Error as e:
        server.logger.error(f"连接MySQL数据库时出错: {e}")
        return None
    except Exception as e:
        server.logger.error(f"连接MySQL数据库时发生未知错误: {e}")
        return None



                        
def get_online_players(server: PluginServerInterface):

    try:
        conn = get_mysql_connection(server)
        if conn is None:

            return []
            
        cursor = conn.cursor()

        server_id = config.get("server_id", "server_1")
        cursor.execute('''
            SELECT DISTINCT player_name FROM player_sessions
            WHERE server_id = %s AND leave_time IS NULL
        ''', (server_id,))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [row[0] for row in rows]
    except Exception as e:
        return []

def save_server_startup_time_to_file(startup_time):
    try:
        server_dir = os.path.join('config', 'server_status')
        os.makedirs(server_dir, exist_ok=True)
        startup_time_file = os.path.join(server_dir, 'startup_time.json')
        with open(startup_time_file, 'w') as f:
            json.dump({"startup_time": startup_time, "pid": os.getpid()}, f)
    except Exception as e:
        pass  


def load_server_startup_time_from_file():
    try:
        startup_time_file = os.path.join('config', 'server_status', 'startup_time.json')
        if os.path.exists(startup_time_file):
            with open(startup_time_file, 'r') as f:
                data = json.load(f)
                saved_pid = data.get("pid")
                if saved_pid == os.getpid():
                    return data.get("startup_time", time.time())
                else:
                    startup_time = init_server_startup_time()
                    save_server_startup_time_to_file(startup_time)
                    return startup_time
        else:
            startup_time = init_server_startup_time()
            save_server_startup_time_to_file(startup_time)
            return startup_time
    except Exception as e:
        startup_time = init_server_startup_time()
        save_server_startup_time_to_file(startup_time)
        return startup_time


def get_server_startup_time():
    global server_startup_time
    return server_startup_time

server_startup_time = load_server_startup_time_from_file()

startup_time = time.time()

DEFAULT_CONFIG = {
    "server_name": "Minecraft Server",
    "web_server_url": "http://localhost:5000/api/server_status",
    "server_id": "server_1",
    "report_interval": 60,
    "bot_prefixes": ["假的bot", "假的Bot_"]  
}

config = None

reporting = False

server_interface = None

def on_load(server: PluginServerInterface, prev_module):
    global startup_time, config, DB_PATH, server_interface
    server_interface = server  
    
    # 先初始化配置
    config = server.load_config_simple('config.json', default_config=DEFAULT_CONFIG)
    DB_PATH = config.get("database_path", "config/server_status/player_records.db")
    
    startup_time = time.time()
    server.logger.info('服务器状态插件已加载')
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
        .then(
            Literal('players')
            .requires(lambda src: src.has_permission(2))
            .runs(lambda src: show_online_players(src))
        )
    )
    server.register_help_message('!!status', '查看服务器运行时间和在线玩家数量')
    server.register_help_message('!!status connect', '测试与后端服务器的连接')
    server.register_help_message('!!status bots', '查看在线的假人玩家列表')
    server.register_help_message('!!status players', '查看当前在线的真实玩家列表')


    server.register_event_listener('PlayerJoined', on_player_joined)
    server.register_event_listener('PlayerLeft', on_player_left)


    start_reporting(server)
    

    auto_connect_to_backend(server)


def on_unload(server: PluginServerInterface):
    global reporting
    reporting = False
    server.logger.info("服务器状态插件已卸载")


@new_thread("ServerStatus-AutoConnect")
def auto_connect_to_backend(server: PluginServerInterface):
    try:
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
            pass
        else:
            pass
            
        time.sleep(2)
        send_full_status_update(server)
        
    except requests.exceptions.Timeout:
        pass
    except requests.exceptions.ConnectionError:
        pass
    except Exception as e:
        pass


def send_full_status_update(server: PluginServerInterface):
    try:
        status_data = build_status_data(server)
        response = requests.post(
            config["web_server_url"],
            json=status_data,
            timeout=10
        )
        
        if response.status_code == 200:
            pass
        else:
            pass
    except Exception as e:
        pass


@new_thread("ServerStatus-Query") 
def on_status_command(src: CommandSource):
    src.reply(get_server_info(src.get_server()))


@new_thread("ServerStatus-Bots")
def show_bots(src: CommandSource):
    player_list = get_filtered_player_list()
    bots = player_list["bots"]
    
    if bots:
        src.reply(f"§7======= §6假人玩家列表 §7=======")
        for bot in bots:
            src.reply(f"§7- §6{bot}")
        src.reply(f"§7=========================")
    else:
        src.reply("§7当前没有在线的假人玩家")


@new_thread("ServerStatus-OnlinePlayers")
def show_online_players(src: CommandSource):
    online_players = get_online_players()
    
    bot_prefixes = config.get("bot_prefixes", ["假的bot"])
    real_players = []
    for player in online_players:
        is_bot = False
        for prefix in bot_prefixes:
            if player.startswith(prefix):
                is_bot = True
                break
        if not is_bot:
            real_players.append(player)
    
    if real_players:
        src.reply(f"§7======= §6在线真实玩家列表 §7=======")
        for player in real_players:
            src.reply(f"§7- §6{player}")
        src.reply(f"§7=========================")
    else:
        src.reply("§7当前没有在线的真实玩家")


@new_thread("ServerStatus-TestConnection")
def test_connection(src: CommandSource):
    src.reply(f"§7[§6ServerStatus§7] 正在测试与后端服务器的连接...")
    
    try:
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
    global reporting
    reporting = True
    
    time.sleep(5)
    
    try:
        status_data = build_status_data(server)
        response = requests.post(
            config["web_server_url"],
            json=status_data,
            timeout=10
        )
        
        if response.status_code != 200:
            pass
    except Exception as e:
        pass
    
    while reporting:
        try:
            status_data = build_status_data(server)
            
            response = requests.post(
                config["web_server_url"],
                json=status_data,
                timeout=10
            )
            
            if response.status_code != 200:
                pass
                
        except requests.exceptions.RequestException as e:
            pass
        except Exception as e:
            pass
            
        for _ in range(config["report_interval"]):
            if not reporting:
                return
            time.sleep(1)


def get_filtered_player_list():
    import minecraft_data_api as api
    try:
        amount, limit, players = api.get_server_player_list()
        if players is None:
            players = []
            
        real_players = []
        bots = []
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
    def get_memory_used():
        return psutil.virtual_memory().percent
    
    def get_uptime():
        return int(time.time() - get_server_startup_time())
    
    player_info = get_filtered_player_list()
    
    status_data = {
        "server_id": config["server_id"],
        "server_name": config["server_name"],
        "uptime": get_uptime(),
        "memory_usage": get_memory_used(),
        "players": player_info["real_players"],
        "bots": player_info["bots"],
        "player_count": player_info["real_amount"],
        "bot_count": player_info["bots_amount"],
        "last_update": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    }
    
    return status_data


def get_server_info(server: PluginServerInterface) -> RTextList:
    
    def get_menmory_used():
        return f"{psutil.virtual_memory().percent}"
    
    def get_uptime():
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
