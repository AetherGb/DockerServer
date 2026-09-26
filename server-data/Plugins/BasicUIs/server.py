import java
util = java.type("com.kirbymimi.serverCommon.pyUtil.util")

def trigger_client_list_update():
    lst = []
    for client in registered_clients:
        obj = {}
        obj["name"] = client["server_client"].getNickName()
        obj["uid"] = client["server_client"].getInstanceUID()
        obj["ping"] = client.get("ping", -1)
        lst.append(obj)
    util.send_event_to_all_clients("com.kirbymimi.totk_plugins.client_list", lst)

def reload_script(path):
    pass

def client_init(client):
    global registered_clients  
    client_data = {}
    client_data["server_client"] = client
    client_data["ping"] = -1
    registered_clients.append(client_data)
    print("%s connected - save UID: %s" % (client.getNickName(), client.getUID()))
    trigger_client_list_update()

def client_disconnect(client):
    for client_data in registered_clients:
        if client_data["server_client"] == client:
            registered_clients.remove(client_data)
            print("%s disconnected" % client.getNickName())
            trigger_client_list_update()
            return

def init_vars():
    global registered_clients
    if 'registered_clients' in globals():
        return
    registered_clients = []

def receive_client_message(client, data):
    obj = {}
    obj["message"] = str(data).replace('\n', ' ')
    obj["source"] = client.getInstanceUID()
    obj["name"] = client.getNickName()
    util.send_event_to_all_clients("com.kirbymimi.totk_plugins.server_chat", obj)

def on_client_ping(client, data):
    # Fast pong bounce-back for client RTT calculation
    pong_data = {
        "uid": client.getInstanceUID(),
        "time": data.get("time", 0.0) if isinstance(data, dict) else 0.0
    }
    util.send_event_to_all_clients("com.kirbymimi.totk_plugins.pong", pong_data)

def on_client_report_ping(client, data):
    ping_val = data.get("ping", -1) if isinstance(data, dict) else int(data)
    for c in registered_clients:
        if c["server_client"] == client:
            c["ping"] = ping_val
            trigger_client_list_update()
            break

init_vars()

util.register_event("reload_script", reload_script)
util.register_event("client_init", client_init)
util.register_event("client_disconnect", client_disconnect)
util.register_event("com.kirbymimi.totk_plugins.client_chat", receive_client_message)
util.register_event("com.kirbymimi.totk_plugins.ping", on_client_ping)
util.register_event("com.kirbymimi.totk_plugins.report_ping", on_client_report_ping)
trigger_client_list_update()
