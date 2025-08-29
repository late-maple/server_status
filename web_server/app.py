from flask import Flask, request, jsonify, render_template, send_from_directory
from datetime import datetime, timedelta
from flask_cors import CORS
import json
import os
import logging
import mysql.connector
from mysql.connector import Error



# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
# 配置静态文件目录
app.static_folder = 'static'
# 增强CORS支持，允许所有来源
CORS(app, resources={r"/api/*": {"origins": "*"}})

# 使用绝对路径确保文件位置正确
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "server_data.json")

# MySQL数据库配置
MYSQL_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'database': 'server_status',
    'user': 'server_status',
    'password': 'SCTserver',
    'charset': 'utf8mb4',
    'autocommit': True,
    'raise_on_warnings': False
}

logger.info(f"后端工作目录: {os.getcwd()}")

# 设置服务器超时时间（秒），应该比report_interval稍大一些
# 如果report_interval是120秒，我们可以设置超时时间为180秒（3分钟）
SERVER_TIMEOUT = 180  # 3分钟

logger.info(f"基础目录: {BASE_DIR}")
logger.info(f"数据文件路径: {DATA_FILE}")

def is_valid_server_id(server_id):
    """检查服务器ID是否有效"""
    # 过滤掉明显的无效服务器ID
    invalid_ids = ['timestamp', 'status', 'error', 'path', 'message', 'info']
    return server_id and isinstance(server_id, str) and server_id not in invalid_ids and len(server_id) < 50

def sanitize_server_data(data):
    """清理和验证服务器数据，确保数据格式正确"""
    sanitized = {}
    
    # 确保必要的字段存在并具有正确的类型
    server_id = data.get('server_id', 'unknown')
    if not is_valid_server_id(server_id):
        server_id = 'unknown'
    sanitized['server_id'] = server_id
    
    # 内存使用率 - 确保是数字
    memory_usage = data.get('memory_usage')
    if isinstance(memory_usage, (int, float)):
        sanitized['memory_usage'] = memory_usage
    else:
        try:
            sanitized['memory_usage'] = float(memory_usage) if memory_usage is not None else 0
        except (ValueError, TypeError):
            sanitized['memory_usage'] = 0
    
    # 运行时间 - 确保是数字
    uptime = data.get('uptime')
    if isinstance(uptime, (int, float)):
        sanitized['uptime'] = uptime
    else:
        try:
            sanitized['uptime'] = float(uptime) if uptime is not None else 0
        except (ValueError, TypeError):
            sanitized['uptime'] = 0
    
    # 玩家数量 - 确保是整数
    player_count = data.get('player_count')
    if isinstance(player_count, int):
        sanitized['player_count'] = player_count
    else:
        try:
            sanitized['player_count'] = int(player_count) if player_count is not None else 0
        except (ValueError, TypeError):
            sanitized['player_count'] = 0
    
    # 玩家列表 - 确保是字符串列表
    players = data.get('players')
    if isinstance(players, list):
        sanitized['players'] = [str(player) for player in players if player is not None]
    else:
        sanitized['players'] = []
    
    # 最后更新时间
    sanitized['last_update'] = data.get('last_update', datetime.now().isoformat())
    
    # 复制其他字段
    for key, value in data.items():
        if key not in sanitized:
            sanitized[key] = value
            
    return sanitized

class Result:
    """响应结果类"""
    
    def __init__(self, code=200, data=None, message="success"):
        self.code = code
        self.data = data
        self.message = message
    
    @classmethod
    def success(cls, data=None):
        """创建成功的响应结果"""
        return cls(code=200, data=data, message="success")
    
    @classmethod
    def error(cls, message="error", code=500):
        """创建错误的响应结果"""
        return cls(code=code, data=None, message=message)
    
    def to_dict(self):
        """将结果转换为字典格式"""
        return {
            "code": self.code,
            "data": self.data,
            "message": self.message
        }
    
    def to_response(self):
        """将结果转换为Flask响应"""
        return jsonify(self.to_dict())

def create_player_tables():
    """创建玩家相关的数据库表"""
    try:
        logger.info("尝试创建玩家相关数据表")
        conn = get_mysql_connection()
        if conn is None:
            logger.error("无法获取MySQL数据库连接")
            return False
            
        cursor = conn.cursor()
        
        # 创建 player_sessions 表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS player_sessions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                server_id VARCHAR(255) NOT NULL,
                server_name VARCHAR(255) NOT NULL,
                player_name VARCHAR(255) NOT NULL,
                join_time DOUBLE NOT NULL,
                login_date DATETIME NOT NULL,
                leave_time DOUBLE,
                logout_date DATETIME,
                play_duration DOUBLE,
                INDEX idx_server_player (server_id, player_name),
                INDEX idx_login_time (join_time),
                INDEX idx_logout_time (leave_time)
            )
        ''')
        
        # 创建 player_stats 表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS player_stats (
                id INT AUTO_INCREMENT PRIMARY KEY,
                server_id VARCHAR(255) NOT NULL,
                server_name VARCHAR(255) NOT NULL,
                player_name VARCHAR(255) NOT NULL,
                total_play_time DOUBLE DEFAULT 0,
                total_sessions INT DEFAULT 0,
                last_play_time DATETIME,
                UNIQUE KEY unique_server_player (server_id, player_name),
                INDEX idx_server (server_id),
                INDEX idx_player (player_name),
                INDEX idx_last_play_time (last_play_time)
            )
        ''')
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info("玩家相关数据表创建成功")
        return True
    except Exception as e:
        logger.error(f"创建玩家相关数据表时出错: {e}")
        logger.exception(e)
        return False

def get_mysql_connection():
    """获取MySQL数据库连接"""
    try:
        logger.info(f"尝试连接MySQL数据库: {MYSQL_CONFIG['host']}:{MYSQL_CONFIG['database']}")
        # 添加连接超时设置
        connection_config = MYSQL_CONFIG.copy()
        connection_config['connection_timeout'] = 10  # 10秒连接超时
        connection_config['autocommit'] = True
        
        connection = mysql.connector.connect(**connection_config)
        logger.info("MySQL数据库连接成功")
        return connection
    except mysql.connector.Error as e:
        logger.error(f"MySQL数据库连接错误: {e}")
        logger.error(f"错误代码: {e.errno}")
        logger.error(f"SQL状态: {e.sqlstate}")
        if e.errno == mysql.connector.errorcode.ER_ACCESS_DENIED_ERROR:
            logger.error("用户名或密码错误")
        elif e.errno == mysql.connector.errorcode.ER_BAD_DB_ERROR:
            logger.error("数据库不存在")
        elif e.errno == mysql.connector.errorcode.ER_HOSTNAME:
            logger.error("主机未找到")
        elif e.errno == 2003:  # CR_CONNECTION_TIMEOUT is 2003
            logger.error("连接超时")
        else:
            logger.error(f"其他数据库错误: {e.msg}")
        return None
    except Exception as e:
        logger.error(f"连接MySQL数据库时发生未知错误: {e}")
        logger.exception(e)
        return None

def load_server_data():
    """加载服务器数据"""
    logger.info(f"尝试加载数据文件: {DATA_FILE}")
    logger.info(f"数据文件是否存在: {os.path.exists(DATA_FILE)}")
    logger.info(f"数据文件大小: {os.path.getsize(DATA_FILE) if os.path.exists(DATA_FILE) else 'N/A'} 字节")
    
    if os.path.exists(DATA_FILE):
        try:
            # 检查文件是否可读
            if not os.access(DATA_FILE, os.R_OK):
                logger.error(f"数据文件不可读: {DATA_FILE}")
                return {}
                
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
                logger.info(f"文件内容长度: {len(content)} 字符")
                
                # 检查文件是否为空
                if not content.strip():
                    logger.warning("数据文件为空")
                    return {}
                
                data = json.loads(content)
                logger.info(f"成功加载数据，包含 {len(data)} 个服务器")
                return data
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误: {e}")
            logger.error(f"错误位置: 行 {e.lineno}, 列 {e.colno}")
            return {}
        except PermissionError as e:
            logger.error(f"权限错误，无法读取数据文件: {e}")
            return {}
        except FileNotFoundError as e:
            logger.error(f"文件未找到错误: {e}")
            return {}
        except Exception as e:
            logger.error(f"加载数据文件时出错: {e}")
            logger.exception(e)
            return {}
    else:
        logger.info("数据文件不存在，返回空字典")
        return {}

def save_server_data(data):
    """保存服务器数据"""
    logger.info(f"尝试保存数据到: {DATA_FILE}")
    logger.info(f"保存的数据: {data}")
    logger.info(f"保存的数据类型: {type(data)}")
    
    try:
        # 验证数据是否可序列化
        json.dumps(data, ensure_ascii=False)
        logger.info("数据验证通过，可以序列化为JSON")
    except TypeError as e:
        logger.error(f"数据不可序列化为JSON: {e}")
        return False
    
    try:
        # 确保目录存在
        data_dir = os.path.dirname(DATA_FILE) if os.path.dirname(DATA_FILE) else '.'
        logger.info(f"数据目录: {data_dir}")
        os.makedirs(data_dir, exist_ok=True)
        logger.info("目录检查完成")
        
        # 检查目录是否可写
        if not os.access(data_dir, os.W_OK):
            logger.error(f"数据目录不可写: {data_dir}")
            return False
        
        # 创建临时文件路径
        temp_file = DATA_FILE + '.tmp'
        logger.info(f"使用临时文件: {temp_file}")
        
        # 先写入临时文件
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # 检查临时文件是否创建成功
        if not os.path.exists(temp_file):
            logger.error("临时文件创建失败")
            return False
            
        # 原子性地替换原文件
        os.replace(temp_file, DATA_FILE)
        logger.info("数据保存成功")
        return True
    except PermissionError as e:
        logger.error(f"权限错误，无法保存数据文件: {e}")
        return False
    except FileNotFoundError as e:
        logger.error(f"文件未找到错误: {e}")
        return False
    except OSError as e:
        logger.error(f"操作系统错误: {e}")
        return False
    except Exception as e:
        logger.error(f"保存数据文件时出错: {e}")
        logger.exception(e)  # 打印完整异常堆栈
        return False

@app.route('/api/server_status', methods=['POST', 'OPTIONS'])
def receive_server_status():
    """接收服务器状态数据"""
    try:
        data = request.json
        logger.info(f"收到数据: {data}")
        
        if not data:
            logger.error("无效的JSON数据")
            return Result.error("无效的JSON数据", 400).to_response()
            
        server_id = data.get('server_id')
        
        if not is_valid_server_id(server_id):
            logger.error(f"无效的server_id: {server_id}")
            return Result.error(f"无效的server_id: {server_id}", 400).to_response()
        
        # 加载现有数据
        server_data = load_server_data()
        logger.info(f"当前服务器数据: {server_data}")
        
        # 清理和验证数据
        cleaned_data = sanitize_server_data(data)
        
        # 更新数据
        cleaned_data['last_update'] = datetime.now().isoformat()
        server_data[server_id] = cleaned_data
        logger.info(f"更新后的数据: {server_data}")
        
        # 保存数据
        save_result = save_server_data(server_data)
        if save_result:
            logger.info(f"收到服务器 {server_id} 的状态更新并成功保存")
            return Result.success().to_response()
        else:
            logger.error(f"收到服务器 {server_id} 的状态更新但保存失败")
            return Result.error("数据保存失败", 500).to_response()
        
    except Exception as e:
        logger.error(f"处理状态更新时出错: {e}")
        logger.exception(e)  # 打印完整异常堆栈
        return Result.error("服务器内部错误", 500).to_response()

@app.route('/')
def dashboard():
    """服务器状态面板"""
    try:
        logger.info("访问仪表板页面")
        logger.info(f"请求来源: {request.remote_addr}")
        logger.info(f"请求头: {dict(request.headers)}")
        return render_template('dashboard.html')
    except Exception as e:
        logger.error(f"加载仪表板时出错: {e}")
        logger.exception(e)
        return "模板文件未找到或出现错误，请检查templates目录中的dashboard.html文件", 500

@app.route('/leaderboard')
def leaderboard():
    """玩家排行榜页面"""
    try:
        logger.info("访问排行榜页面")
        logger.info(f"请求来源: {request.remote_addr}")
        logger.info(f"请求头: {dict(request.headers)}")
        return render_template('leaderboard.html')
    except Exception as e:
        logger.error(f"加载排行榜时出错: {e}")
        logger.exception(e)
        return "模板文件未找到或出现错误，请检查templates目录中的leaderboard.html文件", 500

@app.before_request
def handle_options():
    if request.method == 'OPTIONS':
        response = jsonify({"status": "success"})
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response

# 确保所有API路由都支持OPTIONS方法
@app.route('/api/servers', methods=['GET', 'OPTIONS'])
def api_servers():

    """API接口获取所有服务器状态"""
    try:
        # 记录请求信息用于调试
        logger.info("API服务器数据请求")
        logger.info(f"请求来源: {request.remote_addr}")
        logger.info(f"请求头: {dict(request.headers)}")
        logger.info(f"请求路径: {request.path}")
        logger.info(f"完整URL: {request.url}")
        
        server_data = load_server_data()
        logger.info(f"从文件加载的原始服务器数据: {server_data}")
        
        # 对返回的数据也进行清理，确保格式正确
        cleaned_data = {}
        current_time = datetime.now()
        
        for server_id, data in server_data.items():
            # 过滤掉无效的服务器ID
            if is_valid_server_id(server_id):
                cleaned_data[server_id] = sanitize_server_data(data)
                
                # 检查服务器是否在线
                last_update_str = cleaned_data[server_id].get('last_update')
                if last_update_str:
                    try:
                        last_update = datetime.fromisoformat(last_update_str.replace('Z', '+00:00'))
                        # 如果距离上次更新超过SERVER_TIMEOUT秒，则认为服务器离线
                        if current_time - last_update > timedelta(seconds=SERVER_TIMEOUT):
                            cleaned_data[server_id]['status'] = 'offline'
                        else:
                            cleaned_data[server_id]['status'] = 'online'
                    except ValueError:
                        # 如果日期格式不正确，假设服务器离线
                        cleaned_data[server_id]['status'] = 'offline'
                else:
                    cleaned_data[server_id]['status'] = 'offline'
        
        logger.info(f"处理后的服务器数据: {cleaned_data}")
        response = Result.success(cleaned_data).to_response()
        # 确保响应包含必要的CORS头
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response
    except Exception as e:
        logger.error(f"获取服务器数据时出错: {e}")
        logger.exception(e)
        response = Result.error("服务器内部错误", 500).to_response()
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response

# 添加获取玩家列表的API端点
@app.route('/api/players')
def api_players():
    """API接口获取所有玩家列表"""
    try:
        logger.info("API玩家列表请求")
        
        # 连接数据库并获取玩家统计数据
        conn = get_mysql_connection()
        if conn is None:
            logger.error("无法连接到MySQL数据库")
            return Result.error("无法连接到数据库", 500).to_response()
            
        cursor = conn.cursor(dictionary=True)
        
        # 如果提供了server_id参数，则只返回该服务器的玩家数据
        server_id = request.args.get('server_id')
        
        if server_id:
            logger.info(f"查询特定服务器玩家数据: {server_id}")
            cursor.execute('''
                SELECT
                    player_name,
                    server_id,
                    server_name,
                    total_play_time,
                    total_sessions,
                    last_play_time,
                    CASE
                        WHEN EXISTS (
                            SELECT 1 FROM player_sessions
                            WHERE player_sessions.server_id = player_stats.server_id
                            AND player_sessions.player_name = player_stats.player_name
                            AND logout_time IS NULL
                        ) THEN '在线'
                        ELSE '离线'
                    END as current_status
                FROM player_stats
                WHERE server_id = %s
                ORDER BY total_play_time DESC
            ''', (server_id,))
        else:
            # 返回所有服务器的玩家数据，按玩家名和服务器分组
            logger.info("查询所有服务器玩家数据")
            cursor.execute('''
                SELECT
                    player_name,
                    server_id,
                    server_name,
                    total_play_time,
                    total_sessions,
                    last_play_time,
                    CASE
                        WHEN EXISTS (
                            SELECT 1 FROM player_sessions
                            WHERE player_sessions.server_id = player_stats.server_id
                            AND player_sessions.player_name = player_stats.player_name
                            AND logout_time IS NULL
                        ) THEN '在线'
                        ELSE '离线'
                    END as current_status
                FROM player_stats
                ORDER BY total_play_time DESC
            ''')
        
        players_data = cursor.fetchall()
        logger.info(f"查询到的玩家数据: {players_data}")
        
        # 关闭数据库连接
        cursor.close()
        conn.close()
        
        return Result.success(players_data).to_response()
    except Exception as e:
        logger.error(f"获取玩家列表时出错: {e}")
        logger.exception(e)
        return Result.error("服务器内部错误", 500).to_response()
# 添加获取特定玩家详细记录的API端点
@app.route('/api/players/<player_name>')
def api_player_details(player_name):
    """API接口获取特定玩家的详细记录"""
    try:
        logger.info(f"API玩家 {player_name} 详细记录请求")
        
        # 验证玩家名称
        if not player_name or '..' in player_name or '/' in player_name or '\\' in player_name:
            return Result.error("无效的玩家名称", 400).to_response()
        
        # 连接数据库
        conn = get_mysql_connection()
        if conn is None:
            logger.error("无法连接到MySQL数据库")
            return Result.error("无法连接到数据库", 500).to_response()
            
        cursor = conn.cursor(dictionary=True)
        
        # 获取玩家在所有服务器上的统计信息
        cursor.execute('''
            SELECT
                server_id,
                server_name,
                player_name,
                total_play_time,
                total_sessions,
                last_play_time
            FROM player_stats
            WHERE player_name = %s
            ORDER BY total_play_time DESC
        ''', (player_name,))
        
        player_stats_rows = cursor.fetchall()
        if not player_stats_rows:
            cursor.close()
            conn.close()
            return Result.error("未找到该玩家的记录", 404).to_response()
        
        # 获取玩家在所有服务器上的会话记录
        cursor.execute('''
            SELECT
                server_id,
                server_name,
                join_time,
                leave_time,
                play_duration
            FROM player_sessions
            WHERE player_name = %s
            ORDER BY join_time DESC
            LIMIT 100  -- 限制最多返回100条记录
        ''', (player_name,))
        
        session_records = cursor.fetchall()
        
        # 关闭数据库连接
        cursor.close()
        conn.close()
        
        # 处理记录数据
        processed_records = []
        for record in session_records:
            play_duration = record['play_duration']
            processed_records.append({
                "server_id": record['server_id'],
                "server_name": record['server_name'],
                "login_date": record['join_time'].isoformat() if record['join_time'] else None,
                "logout_date": record['leave_time'].isoformat() if record['leave_time'] else None,
                "play_duration": play_duration,  # 秒
                "play_duration_formatted": format_duration(play_duration) if play_duration is not None else None
            })
        
        # 处理统计数据
        stats_data = []
        for stat in player_stats_rows:
            stats_data.append({
                "server_id": stat['server_id'],
                "server_name": stat['server_name'],
                "total_sessions": stat['total_sessions'],
                "total_play_time": stat['total_play_time'],  # 秒
                "total_play_time_formatted": format_duration(stat['total_play_time']),
                "last_play_time": stat['last_play_time']
            })
        
        player_data = {
            "player_name": player_name,
            "stats": stats_data,
            "records": processed_records
        }
        
        logger.info(f"返回玩家 {player_name} 的详细数据: {player_data}")
        return Result.success(player_data).to_response()
    except Exception as e:
        logger.error(f"获取玩家 {player_name} 详细记录时出错: {e}")
        logger.exception(e)
        return Result.error("服务器内部错误", 500).to_response()

# 添加获取特定服务器玩家记录的API端点
@app.route('/api/servers/<server_id>/players')
def api_server_players(server_id):
    """API接口获取特定服务器的玩家列表"""
    try:
        logger.info(f"API服务器 {server_id} 玩家列表请求")
        
        # 连接数据库并获取玩家统计数据
        conn = get_mysql_connection()
        if conn is None:
            logger.error("无法连接到MySQL数据库")
            return Result.error("无法连接到数据库", 500).to_response()
            
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute('''
            SELECT
                player_name,
                server_id,
                server_name,
                total_play_time,
                total_sessions,
                last_play_time,
                CASE
                    WHEN EXISTS (
                        SELECT 1 FROM player_sessions
                        WHERE player_sessions.server_id = player_stats.server_id
                        AND player_sessions.player_name = player_stats.player_name
                        AND logout_time IS NULL
                    ) THEN '在线'
                    ELSE '离线'
                END as current_status
            FROM player_stats
            WHERE server_id = %s
            ORDER BY total_play_time DESC
        ''', (server_id,))
        
        players_data = cursor.fetchall()
        
        # 关闭数据库连接
        cursor.close()
        conn.close()
        
        logger.info(f"返回服务器 {server_id} 的玩家数据: {players_data}")
        return Result.success(players_data).to_response()
    except Exception as e:
        logger.error(f"获取服务器 {server_id} 玩家列表时出错: {e}")
        logger.exception(e)
        return Result.error("服务器内部错误", 500).to_response()

def format_duration(seconds):
    """格式化持续时间"""
    if seconds is None:
        return "N/A"
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    if hours > 0:
        return f"{hours}小时{minutes}分钟{secs}秒"
    elif minutes > 0:
        return f"{minutes}分钟{secs}秒"
    else:
        return f"{secs}秒"

# 添加获取玩家列表（包含距离上次游戏时间）的API端点
@app.route('/api/players_with_last_played')
def api_players_with_last_played():
    """API接口获取所有玩家列表，包含距离上次游戏时间"""
    try:
        logger.info("API玩家列表请求（包含距离上次游戏时间）")
        logger.info(f"请求方法: {request.method}")
        logger.info(f"请求路径: {request.path}")
        logger.info(f"完整URL: {request.url}")
        logger.info(f"请求参数: {request.args}")
        
        # 连接数据库并获取玩家统计数据
        conn = get_mysql_connection()
        if conn is None:
            logger.error("无法连接到MySQL数据库")
            return Result.error("无法连接到数据库", 500).to_response()
            
        cursor = conn.cursor(dictionary=True)
        
        # 如果提供了server_id参数，则只返回该服务器的玩家数据
        server_id = request.args.get('server_id')
        
        if server_id:
            logger.info(f"查询特定服务器玩家数据: {server_id}")
            cursor.execute('''
                SELECT
                    player_name,
                    server_id,
                    server_name,
                    total_play_time,
                    total_sessions,
                    last_play_time,
                    CASE
                        WHEN EXISTS (
                            SELECT 1 FROM player_sessions
                            WHERE player_sessions.server_id = player_stats.server_id
                            AND player_sessions.player_name = player_stats.player_name
                            AND logout_time IS NULL
                        ) THEN '在线'
                        ELSE '离线'
                    END as current_status
                FROM player_stats
                WHERE server_id = %s
                ORDER BY total_play_time DESC
            ''', (server_id,))
        else:
            # 返回所有服务器的玩家数据，按玩家名和服务器分组
            logger.info("查询所有服务器玩家数据")
            cursor.execute('''
                SELECT
                    player_name,
                    server_id,
                    server_name,
                    total_play_time,
                    total_sessions,
                    last_play_time,
                    CASE
                        WHEN EXISTS (
                            SELECT 1 FROM player_sessions
                            WHERE player_sessions.server_id = player_stats.server_id
                            AND player_sessions.player_name = player_stats.player_name
                            AND logout_time IS NULL
                        ) THEN '在线'
                        ELSE '离线'
                    END as current_status
                FROM player_stats
                ORDER BY total_play_time DESC
            ''')
        
        rows = cursor.fetchall()
        players_data = []
        
        # 获取当前时间
        current_time = datetime.now()
        
        for row in rows:
            player_dict = row
            
            # 计算距离上次游戏的时间
            last_play_time = player_dict.get('last_play_time')
            if last_play_time:
                # 如果last_play_time已经是datetime对象，直接使用它
                if isinstance(last_play_time, datetime):
                    time_since_last_played = (current_time - last_play_time).total_seconds()
                    player_dict['time_since_last_played'] = time_since_last_played
                    player_dict['time_since_last_played_formatted'] = format_duration(time_since_last_played)
                else:
                    # 如果last_play_time是字符串，尝试解析它
                    try:
                        last_play_time = datetime.strptime(last_play_time, "%Y-%m-%d %H:%M:%S")
                        time_since_last_played = (current_time - last_play_time).total_seconds()
                        player_dict['time_since_last_played'] = time_since_last_played
                        player_dict['time_since_last_played_formatted'] = format_duration(time_since_last_played)
                    except ValueError:
                        # 如果日期格式不正确，设置为None
                        player_dict['time_since_last_played'] = None
                        player_dict['time_since_last_played_formatted'] = "N/A"
            else:
                player_dict['time_since_last_played'] = None
                player_dict['time_since_last_played_formatted'] = "N/A"
            
            players_data.append(player_dict)
        
        # 关闭数据库连接
        cursor.close()
        conn.close()
        
        logger.info(f"查询到的玩家数据: {players_data}")
        
        return Result.success(players_data).to_response()
    except Exception as e:
        logger.error(f"获取玩家列表时出错: {e}")
        logger.exception(e)
        return Result.error("服务器内部错误", 500).to_response()

# 添加获取距离上次游戏时间最长的前10位玩家的API端点
@app.route('/api/players/leaderboard')
def api_players_leaderboard():
    """API接口获取距离上次游戏时间最长的前10位玩家"""
    try:
        logger.info("API玩家排行榜请求")
        
        # 检查是否需要过滤假人玩家
        filter_bots = request.args.get('filter_bots', 'false').lower() == 'true'
        logger.info(f"过滤假人玩家: {filter_bots}")
        
        # 连接数据库并获取玩家统计数据
        conn = get_mysql_connection()
        if conn is None:
            logger.error("无法连接到MySQL数据库")
            return Result.error("无法连接到数据库", 500).to_response()
            
        cursor = conn.cursor(dictionary=True)
        
        # 如果提供了server_id参数，则只返回该服务器的玩家数据
        server_id = request.args.get('server_id')
        
        if server_id:
            logger.info(f"查询特定服务器玩家排行榜: {server_id}")
            # 构建基础查询
            base_query = '''
                SELECT
                    player_name,
                    server_id,
                    server_name,
                    total_play_time,
                    total_sessions,
                    last_play_time,
                    CASE
                        WHEN EXISTS (
                            SELECT 1 FROM player_sessions
                            WHERE player_sessions.server_id = player_stats.server_id
                            AND player_sessions.player_name = player_stats.player_name
                            AND leave_time IS NULL
                        ) THEN '在线'
                        ELSE '离线'
                    END as current_status
                FROM player_stats
                WHERE server_id = %s AND last_play_time IS NOT NULL
            '''
            
            # 如果需要过滤假人，添加过滤条件
            if filter_bots:
                # 假设假人玩家名以特定前缀开头，这里使用常见的假人前缀
                base_query += " AND player_name NOT LIKE '假人%' AND player_name NOT LIKE 'Bot%' AND player_name NOT LIKE 'bot%'"
            
            base_query += " ORDER BY last_play_time ASC LIMIT 10"
            
            params = (server_id,)
            cursor.execute(base_query, params)
        else:
            # 返回所有服务器的综合玩家数据，按玩家名分组，取最后游戏时间最新的记录
            logger.info("查询所有服务器玩家综合排行榜")
            if filter_bots:
                cursor.execute('''
                    SELECT 
                        player_name,
                        GROUP_CONCAT(DISTINCT server_name SEPARATOR ', ') as server_names,
                        SUM(total_play_time) as total_play_time,
                        SUM(total_sessions) as total_sessions,
                        MAX(last_play_time) as last_play_time,
                        CASE
                            WHEN EXISTS (
                                SELECT 1 FROM player_sessions
                                WHERE player_sessions.player_name = ps_agg.player_name
                                AND leave_time IS NULL
                            ) THEN '在线'
                            ELSE '离线'
                        END as current_status
                    FROM (
                        SELECT 
                            player_name,
                            server_name,
                            total_play_time,
                            total_sessions,
                            last_play_time
                        FROM player_stats
                        WHERE last_play_time IS NOT NULL
                        AND player_name NOT LIKE '假人%' 
                        AND player_name NOT LIKE 'Bot%' 
                        AND player_name NOT LIKE 'bot%'
                    ) as ps_agg
                    GROUP BY player_name
                    ORDER BY last_play_time ASC
                    LIMIT 10
                ''')
            else:
                cursor.execute('''
                    SELECT 
                        player_name,
                        GROUP_CONCAT(DISTINCT server_name SEPARATOR ', ') as server_names,
                        SUM(total_play_time) as total_play_time,
                        SUM(total_sessions) as total_sessions,
                        MAX(last_play_time) as last_play_time,
                        CASE
                            WHEN EXISTS (
                                SELECT 1 FROM player_sessions
                                WHERE player_sessions.player_name = ps_agg.player_name
                                AND leave_time IS NULL
                            ) THEN '在线'
                            ELSE '离线'
                        END as current_status
                    FROM (
                        SELECT 
                            player_name,
                            server_name,
                            total_play_time,
                            total_sessions,
                            last_play_time
                        FROM player_stats
                        WHERE last_play_time IS NOT NULL
                    ) as ps_agg
                    GROUP BY player_name
                    ORDER BY last_play_time ASC
                    LIMIT 10
                ''')
        
        rows = cursor.fetchall()
        players_data = []
        
        # 获取当前时间
        current_time = datetime.now()
        
        for row in rows:
            player_dict = row
            
            # 计算距离上次游戏的时间
            last_play_time = player_dict.get('last_play_time')
            if last_play_time:
                # 如果last_play_time已经是datetime对象，直接使用它
                if isinstance(last_play_time, datetime):
                    time_since_last_played = (current_time - last_play_time).total_seconds()
                    player_dict['time_since_last_played'] = time_since_last_played
                    player_dict['time_since_last_played_formatted'] = format_duration(time_since_last_played)
                else:
                    # 如果last_play_time是字符串，尝试解析它
                    try:
                        last_play_time = datetime.strptime(last_play_time, "%Y-%m-%d %H:%M:%S")
                        time_since_last_played = (current_time - last_play_time).total_seconds()
                        player_dict['time_since_last_played'] = time_since_last_played
                        player_dict['time_since_last_played_formatted'] = format_duration(time_since_last_played)
                    except ValueError:
                        # 如果日期格式不正确，设置为None
                        player_dict['time_since_last_played'] = None
                        player_dict['time_since_last_played_formatted'] = "N/A"
            else:
                player_dict['time_since_last_played'] = None
                player_dict['time_since_last_played_formatted'] = "N/A"
            players_data.append(player_dict)
        
        # 关闭数据库连接
        cursor.close()
        conn.close()
        
        logger.info(f"查询到的玩家排行榜数据: {players_data}")
        
        response = Result.success(players_data).to_response()
        # 确保响应包含必要的CORS头
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response
    except Exception as e:
        logger.error(f"获取玩家排行榜时出错: {e}")
        logger.exception(e)
        response = Result.error("服务器内部错误", 500).to_response()
        # 确保错误响应也包含必要的CORS头
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response
# 添加获取游戏时长周榜的API端点
@app.route('/api/players/leaderboard/weekly')
def api_players_weekly_leaderboard():
    """API接口获取游戏时长周榜前10位玩家"""
    try:
        logger.info("API玩家周榜请求")
        
        # 连接数据库并获取玩家统计数据
        conn = get_mysql_connection()
        if conn is None:
            logger.error("无法连接到MySQL数据库")
            return Result.error("无法连接到数据库", 500).to_response()
            
        cursor = conn.cursor(dictionary=True)
        
        # 计算一周前的时间
        one_week_ago = datetime.now() - timedelta(days=7)
        
        # 查询一周内游戏时长最多的玩家，按玩家名分组并汇总所有服务器的时长
        logger.info("查询游戏时长周榜")
        cursor.execute('''
            SELECT
                ps.player_name,
                SUM(ps.play_duration) as weekly_play_time,
                MAX(ps.join_time) as last_play_time,
                CASE
                    WHEN EXISTS (
                        SELECT 1 FROM player_sessions
                        WHERE player_sessions.player_name = ps.player_name
                        AND leave_time IS NULL
                    ) THEN '在线'
                    ELSE '离线'
                END as current_status,
                COALESCE(SUM(stats.total_play_time), 0) as total_play_time
            FROM player_sessions ps
            JOIN player_stats stats ON ps.player_name = stats.player_name AND ps.server_id = stats.server_id
            WHERE ps.join_time >= %s
            GROUP BY ps.player_name
            ORDER BY weekly_play_time DESC
            LIMIT 10
        ''', (one_week_ago,))
        
        rows = cursor.fetchall()
        players_data = []
        
        for row in rows:
            player_dict = row
            # 格式化周游戏时长
            player_dict['weekly_play_time_formatted'] = format_duration(row['weekly_play_time'])
            players_data.append(player_dict)
        
        # 关闭数据库连接
        cursor.close()
        conn.close()
        
        logger.info(f"查询到的玩家周榜数据: {players_data}")
        
        return Result.success(players_data).to_response()
    except Exception as e:
        logger.error(f"获取玩家周榜时出错: {e}")
        logger.exception(e)
        return Result.error("服务器内部错误", 500).to_response()

# 添加获取游戏时长月榜的API端点
@app.route('/api/players/leaderboard/monthly')
def api_players_monthly_leaderboard():
    """API接口获取游戏时长月榜前10位玩家"""
    try:
        logger.info("API玩家月榜请求")
        
        # 连接数据库并获取玩家统计数据
        conn = get_mysql_connection()
        if conn is None:
            logger.error("无法连接到MySQL数据库")
            return Result.error("无法连接到数据库", 500).to_response()
            
        cursor = conn.cursor(dictionary=True)
        
        # 计算一个月前的时间
        one_month_ago = datetime.now() - timedelta(days=30)
        
        # 查询一个月内游戏时长最多的玩家，按玩家名分组并汇总所有服务器的时长
        logger.info("查询游戏时长月榜")
        logger.info(f"一个月前的时间: {one_month_ago}")
        cursor.execute('''
            SELECT
                ps.player_name,
                SUM(ps.play_duration) as monthly_play_time,
                MAX(ps.join_time) as last_play_time,
                CASE
                    WHEN EXISTS (
                        SELECT 1 FROM player_sessions
                        WHERE player_sessions.player_name = ps.player_name
                        AND leave_time IS NULL
                    ) THEN '在线'
                    ELSE '离线'
                END as current_status,
                COALESCE(SUM(stats.total_play_time), 0) as total_play_time
            FROM player_sessions ps
            JOIN player_stats stats ON ps.player_name = stats.player_name AND ps.server_id = stats.server_id
            WHERE ps.join_time >= %s
            GROUP BY ps.player_name
            ORDER BY monthly_play_time DESC
            LIMIT 10
        ''', (one_month_ago,))
        
        rows = cursor.fetchall()
        logger.info(f"月榜查询结果原始数据: {rows}")
        players_data = []
        
        # 添加调试信息，查看每个玩家的详细数据
        for row in rows:
            logger.info(f"月榜玩家数据: {row}")
            player_dict = row
            # 格式化月游戏时长
            player_dict['monthly_play_time_formatted'] = format_duration(row['monthly_play_time'])
            players_data.append(player_dict)
        
        # 关闭数据库连接
        cursor.close()
        conn.close()
        
        logger.info(f"查询到的玩家月榜数据: {players_data}")
        
        return Result.success(players_data).to_response()
    except Exception as e:
        logger.error(f"获取玩家月榜时出错: {e}")
        logger.exception(e)
        return Result.error("服务器内部错误", 500).to_response()
    

# 添加一个测试端点来验证API是否正常工作
@app.route('/api/test', methods=['GET', 'OPTIONS'])
def api_test():
    """测试API端点"""
    logger.info("API测试端点被访问")
    logger.info(f"请求来源: {request.remote_addr}")
    logger.info(f"请求头: {dict(request.headers)}")
    return Result.success({"status": "success", "message": "API正常工作"}).to_response()


@app.route('/api/health', methods=['GET', 'OPTIONS'])
def health_check():
    """健康检查端点"""
    logger.info("健康检查端点被访问")
    logger.info(f"请求来源: {request.remote_addr}")
    response = Result.success({"status": "healthy", "message": "服务运行正常"}).to_response()
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return Result.success({"status": "success", "message": "API正常工作"}).to_response()


# 添加一个捕获所有未匹配路由的处理函数，用于调试
@app.errorhandler(404)
def not_found(error):
    logger.info(f"404错误 - 请求路径: {request.path}")
    logger.info(f"完整URL: {request.url}")
    logger.info(f"请求方法: {request.method}")
    return "页面未找到", 404

if __name__ == '__main__':
    logger.info("启动服务器状态Web服务器...")
    logger.info(f"当前工作目录: {os.getcwd()}")
    logger.info(f"BASE_DIR: {BASE_DIR}")
    logger.info(f"DATA_FILE: {DATA_FILE}")
    
    # 创建玩家相关数据表
    if create_player_tables():
        logger.info("玩家相关数据表已准备就绪")
    else:
        logger.error("创建玩家相关数据表失败")
    
    app.run(host='0.0.0.0', port=5000, debug=True)
