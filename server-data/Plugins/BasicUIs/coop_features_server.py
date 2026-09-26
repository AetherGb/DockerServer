# Server-side co-op event dispatcher for Area Bullet-Time (Option A) and Sleep Time-Skip
import java

util = java.type("com.kirbymimi.serverCommon.pyUtil.util")

def on_client_bullet_time(client, data):
    action = data.get("action", "")
    src_uid = client.getInstanceUID()
    
    # Broadcast to peer players within area (Option A: 50m range)
    broadcast_data = {
        "source": src_uid,
        "action": action,
        "x": data.get("x", 0.0),
        "y": data.get("y", 0.0),
        "z": data.get("z", 0.0)
    }
    util.send_event_to_all_clients("com.kirbymimi.totk_plugins.bullet_time_broadcast", broadcast_data)

util.register_event("com.kirbymimi.totk_plugins.bullet_time", on_client_bullet_time)
