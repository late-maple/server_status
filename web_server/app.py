from flask import Flask, request, jsonify, render_template
from datetime import datetime, timedelta
import json
import os
import logging
from flask_cors import CORS

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # 启用CORS支持

# 使用绝对路径确保文件位置正确
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "server_data.json")

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

def load_server_data():
    """加载服务器数据"""
    logger.info(f"尝试加载数据文件: {DATA_FILE}")
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f"成功加载数据: {data}")
                return data
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误: {e}")
            return {}
        except Exception as e:
            logger.error(f"加载数据文件时出错: {e}")
            return {}
    logger.info("数据文件不存在，返回空字典")
    return {}

def save_server_data(data):
    """保存服务器数据"""
    logger.info(f"尝试保存数据到: {DATA_FILE}")
    logger.info(f"保存的数据: {data}")
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(DATA_FILE) if os.path.dirname(DATA_FILE) else '.', exist_ok=True)
        logger.info("目录检查完成")
        
        # 尝试写入文件
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("数据保存成功")
        return True
    except PermissionError as e:
        logger.error(f"权限错误，无法保存数据文件: {e}")
        return False
    except FileNotFoundError as e:
        logger.error(f"文件未找到错误: {e}")
        return False
    except Exception as e:
        logger.error(f"保存数据文件时出错: {e}")
        logger.exception(e)  # 打印完整异常堆栈
        return False

@app.route('/api/server_status', methods=['POST'])
def receive_server_status():
    """接收服务器状态数据"""
    try:
        data = request.json
        logger.info(f"收到数据: {data}")
        
        if not data:
            logger.error("无效的JSON数据")
            return jsonify({"error": "无效的JSON数据"}), 400
            
        server_id = data.get('server_id')
        
        if not is_valid_server_id(server_id):
            logger.error(f"无效的server_id: {server_id}")
            return jsonify({"error": f"无效的server_id: {server_id}"}), 400
        
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
            return jsonify({"status": "success"})
        else:
            logger.error(f"收到服务器 {server_id} 的状态更新但保存失败")
            return jsonify({"status": "error", "message": "数据保存失败"}), 500
        
    except Exception as e:
        logger.error(f"处理状态更新时出错: {e}")
        logger.exception(e)  # 打印完整异常堆栈
        return jsonify({"error": "服务器内部错误"}), 500

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

@app.route('/api/servers')
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
        
        logger.info(f"返回服务器数据: {cleaned_data}")
        response = jsonify(cleaned_data)
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
    except Exception as e:
        logger.error(f"获取服务器数据时出错: {e}")
        logger.exception(e)
        return jsonify({"error": "服务器内部错误"}), 500

# 添加一个测试端点来验证API是否正常工作
@app.route('/api/test')
def api_test():
    """测试API端点"""
    logger.info("API测试端点被访问")
    logger.info(f"请求来源: {request.remote_addr}")
    logger.info(f"请求头: {dict(request.headers)}")
    response = jsonify({"status": "success", "message": "API正常工作"})
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response

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
    app.run(host='0.0.0.0', port=5000, debug=True)