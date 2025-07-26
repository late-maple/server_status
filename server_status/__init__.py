from mcdreforged.api.all import *
import time
import psutil



def on_load(server: PluginServerInterface, prev_module):
    server.logger.info('服务器状态插件已加载')
    server.register_command(
        Literal('!!status')
        .runs(
            lambda src: on_status_command(src)
        )
    )
    server.register_help_message('!!status', '查看服务器运行时间和在线玩家数量')


@new_thread("ServerStatus-Query") 
def on_status_command(src: CommandSource):
    src.reply(get_server_info(src.get_server()))


def get_server_info(server: PluginServerInterface) -> RTextList:
    
    def get_menmory_used():
        return f"{psutil.virtual_memory().percent}"
    
    def get_player_list():
        import minecraft_data_api as api
        try:
            amount, limit, players = api.get_server_player_list() 
            return {
                "players": players,
                "amount": amount
            }
        except Exception as e:
            return {"players": ["获取失败"], "amount": 0}
        
    player_list = get_player_list()
    players = player_list["players"]
    player_count = player_list["amount"]
    


    return RTextList(
        f"§7============ §6服务器状态 §7============\n",
        f"§6内存使用率§7: {get_menmory_used()}%\n",
        f"§6玩家列表§7: {players}\n",
        f"§6玩家总数§7: {player_count}\n",
        f"§7==================================="
    )
