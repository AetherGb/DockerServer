import totk
import math
import imgui
import util
import random
import unsafe
import nn

player_list = []
messages = []
amazing_font = None
ui_enabled = False
keyboard_opened = False
a_and_b_held_time = 0
disable_font = False
ping_timer = 0.0
last_ping_rtt = -1

def update_client_list(arg):
    global player_list
    player_list = arg

def check_ping():
    global ping_timer
    ping_timer += totk.get_delta_time()
    if ping_timer >= 1.5:
        ping_timer = 0.0
        try:
            util.send_event_to_server("com.kirbymimi.totk_plugins.ping", {"time": a_and_b_held_time})
        except Exception:
            pass

def on_pong(data):
    global last_ping_rtt
    try:
        me = totk.get_player_synced_actor()
        if me is not None and "uid" in data and data.get("uid") != me.player_instance_uid:
            return  # Pong response is for another player, ignore
        t_sent = data.get("time", 0.0)
        rtt = max(1, int(abs(a_and_b_held_time - t_sent) * 1000.0))
        if rtt > 999:
            rtt = 999
        last_ping_rtt = rtt
        util.send_event_to_server("com.kirbymimi.totk_plugins.report_ping", {"ping": rtt})
    except Exception:
        pass

def calc():
    global a_and_b_held_time
    global ui_enabled
    global keyboard_opened
    global amazing_font

    check_ping()

    for obj in player_list:
        obj["img_res"] = util.load_resource("icons/" + str(obj["uid"]))
    if amazing_font is None and totk.is_imgui_initilized():
        res = util.load_resource("Plugins/BasicUIs/Font.ttf")
        if res.is_ready():
            amazing_font = imgui.init_font(res.get_data(), 32)
            totk.rebuild_imgui_atlas()
            res.invalidate()
    controller = totk.get_controller(0)
    if controller.is_a_held() and controller.is_b_held():
        a_and_b_held_time += totk.get_delta_time()
        if a_and_b_held_time > 0.5:
            a_and_b_held_time = 0
            ui_enabled = not ui_enabled
    else:
        a_and_b_held_time = 0
    for obj in player_list:
        if not obj["img_res"].is_ready():
            continue
        if not "img" in obj:
            obj["img"] = totk.png_to_image(obj["img_res"].get_data())
    if ui_enabled:
        if controller.is_a_held() and controller.is_x_held():
            if not keyboard_opened:
                msg = nn.keyboard_request_text()
                if len(msg) != 0:
                    util.send_event_to_server("com.kirbymimi.totk_plugins.client_chat", msg)
                keyboard_opened = True
        else:
            keyboard_opened = False

def render_hud_minimap():
    me = totk.get_player_synced_actor()
    if me is None:
        return
    my_pos = me.position
    camera = totk.get_camera()
    matrix = camera.get_matrix()

    sw = totk.get_screen_width()
    sh = totk.get_screen_height()
    scale_factor = sh / 720.0
    
    # In TOTK, the circular minimap is located at bottom-right of the HUD
    mc_x = sw - (105.0 * scale_factor)
    mc_y = sh - (90.0 * scale_factor)
    mr = 62.0 * scale_factor
    radar_range = 100.0  # In-game meters represented by the minimap radius

    draw_list = imgui.get_foreground_draw_list()

    for synced_actor in totk.get_synced_actors():
        if synced_actor == me:
            continue
        if synced_actor.properties_name != "PlayerPuppet":
            continue
        
        # Transform delta position into camera space
        rel_pos = synced_actor.position - my_pos
        cam_rel = matrix.transpose() * rel_pos
        
        dx = cam_rel.x
        dz = -cam_rel.z
        dist_2d = math.sqrt(dx * dx + dz * dz)
        
        if dist_2d <= radar_range:
            screen_x = mc_x + (dx / radar_range) * mr
            screen_y = mc_y - (dz / radar_range) * mr
        else:
            # Clamp to perimeter if beyond minimap radar range
            angle = math.atan2(dz, dx)
            screen_x = mc_x + math.cos(angle) * (mr - 6.0 * scale_factor)
            screen_y = mc_y - math.sin(angle) * (mr - 6.0 * scale_factor)
            
        instance_uid = synced_actor.player_instance_uid
        for val in player_list:
            if val["uid"] != instance_uid:
                continue
            if "img" in val:
                iw = 24.0 * scale_factor
                ih = 24.0 * scale_factor
                # Draw subtle background dot under icon for visibility
                draw_list.add_circle_filled(util.Vec3(screen_x, screen_y, 0), 14.0 * scale_factor, 0xDD000000)
                draw_list.add_circle(util.Vec3(screen_x, screen_y, 0), 14.0 * scale_factor, 0xFF00E5FF, 16, 2.0 * scale_factor)
                draw_list.add_image(val["img"].texture_handle, 
                                    util.Vec3(screen_x + iw/2, screen_y - ih/2, 0), 
                                    util.Vec3(screen_x - iw/2, screen_y + ih/2, 0), 
                                    util.Vec3(1, 0, 0), util.Vec3(0, 1, 0), 0xFFFFFFFF)
            else:
                # Fallback cyan dot if profile picture is not yet loaded
                draw_list.add_circle_filled(util.Vec3(screen_x, screen_y, 0), 8.0 * scale_factor, 0xFF00E5FF)
            break

def render_minimap_icons():
    map_ui = totk.get_map_screen()
    if map_ui.is_open():
        # Full-screen map rendering
        for synced_actor in totk.get_synced_actors():
            if synced_actor == totk.get_player_synced_actor():
                continue
            if synced_actor.properties_name != "PlayerPuppet":
                continue
            out_pos = util.Vec3(0)
            if not conv_world_to_map(synced_actor.position, out_pos):
                continue
            instance_uid = synced_actor.player_instance_uid
            for val in player_list:
                if val["uid"] is not instance_uid:
                    continue
                if "img" in val:
                    out_pos = out_pos * util.Vec3(totk.get_screen_width(), totk.get_screen_height(), 1)
                    img_x = out_pos.x + 16
                    img_y = out_pos.y - 16
                    img_w = 32
                    img_h = 32
                    draw_list = imgui.get_foreground_draw_list()
                    draw_list.add_image(val["img"].texture_handle, util.Vec3(img_x, img_y, 0), util.Vec3(img_x - img_w, img_y + img_h, 0), util.Vec3(1, 0, 0), util.Vec3(0, 1, 0), 0xFFE8E8E8)
    else:
        # HUD circular minimap rendering when running around the game world
        render_hud_minimap()

def conv_world_to_map(pos, out):
    map_ui = totk.get_map_screen()
    if not map_ui.is_open():
        return False
    if pos.y > 920:
        if map_ui.layer != 0:
            return False
    elif pos.y > -60:
        if map_ui.layer != 1:
            return False
    elif map_ui.layer != 2:
        return False
    zoom = map_ui.zoom
    map_pos = map_ui.camera_position
    relative = util.Vec3(pos.x, -pos.z, 0) + -map_pos
    out.x = relative.x / (320 / zoom)
    out.y = relative.y / (180 / zoom)
    out.x = out.x / 2 + 0.5
    out.y = -out.y / 2 + 0.5
    out.z = zoom
    return True

def render_name_tags():
    global player_list
    camera = totk.get_camera()
    origin_pos = camera.get_position()
    previous_font_size = imgui.get_draw_list_shared_data().font_size
    for synced_actor in totk.get_synced_actors():
        if synced_actor == totk.get_player_synced_actor():
            continue
        actor = synced_actor.game_actor
        if synced_actor.properties_name != "PlayerPuppet":
            continue
        dist = 0
        dist = (actor.position - origin_pos).length()
        if (dist > 20.0):
            continue
        scale = 0.5
        if (dist < 15.0):
            scale = 0.5 + ((15.0 - dist) / 15.0 * 1.5)
        scale = scale * 0.65
        imgui.get_draw_list_shared_data().font_size = previous_font_size * scale
        pos = actor.position
        pos += util.Vec3(0.0, 2.5 + (scale / 20), 0.0)

        matrix = camera.get_matrix()
        result = matrix.transpose() * pos
        
        x = result.x
        y = result.y
        w = result.z
        if (w > 0):
            continue
        x = (x / w) * 1.17
        y = (y / w) * 2.0
        
        x = ((-x + 1.0) / 2.0) * totk.get_screen_width()
        y = ((y + 1.0) / 2.0) * totk.get_screen_height()

        # Find player info and ping
        player_ping = -1
        player_info = None
        instance_uid = synced_actor.player_instance_uid
        for val in player_list:
            if val["uid"] == instance_uid:
                player_info = val
                player_ping = val.get("ping", -1)
                break

        if player_ping >= 0:
            full_display_name = f"{synced_actor.player_name} [{player_ping}ms]"
        else:
            full_display_name = synced_actor.player_name

        text_size = imgui.calc_text_size(full_display_name)
        text_size.x *= scale
        text_size.y *= scale
        x -= text_size.x / 2.0

        alpha = 1.0
        if (dist > 10):
            alpha = (10.0 - (dist - 10.0)) / 10.0
        draw_list = imgui.get_foreground_draw_list()
        draw_list.add_rect_filled(util.Vec3(x - 8 * scale, y - 3 * scale), util.Vec3(x + text_size.x + 8 * scale, y + text_size.y + 3 * scale), int(0xBE * alpha) << 24, 12.0 * scale, 0)
        
        if player_info is not None and "img" in player_info:
            img_x = x - (16 * scale)
            img_y = y
            img_w = 64 * scale
            img_h = 64 * scale
            draw_list.add_image(player_info["img"].texture_handle, util.Vec3(img_x, img_y, 0), util.Vec3(img_x - img_w, img_y + img_h, 0), util.Vec3(1, 0, 0), util.Vec3(0, 1, 0), (int(0xFF * alpha) << 24) | 0x00E8E8E8)
        
        # Color ping: green for low latency, yellow for medium, orange for high
        ping_color = 0x00FFFFFF
        if player_ping >= 0:
            if player_ping < 70:
                ping_color = 0x0088FF88
            elif player_ping < 130:
                ping_color = 0x00FFFF88
            else:
                ping_color = 0x00FFAA66

        draw_list.add_text(util.Vec3(x, y, 0), (int(0xFF * alpha) << 24) | ping_color, full_display_name)
    imgui.get_draw_list_shared_data().font_size = previous_font_size

def render():
    if not disable_font and amazing_font != None:
        imgui.push_font(amazing_font)
    prev_font_size = imgui.get_draw_list_shared_data().font_size
    render_name_tags()
    render_minimap_icons()
    if not ui_enabled:
        imgui.get_draw_list_shared_data().font_size = prev_font_size
        if not disable_font and amazing_font != None:
            imgui.pop_font()
        return
    imgui.get_draw_list_shared_data().font_size = 32
    score_board_horizontal_margin = 50
    score_board_width = 300
    score_board_height = 500
    score_board_y = 100
    score_board_x = totk.get_screen_width() - score_board_width - score_board_horizontal_margin
    
    imgui.get_foreground_draw_list().add_rect_filled(util.Vec3(score_board_x, score_board_y, 0), util.Vec3(score_board_x + score_board_width, score_board_y + score_board_height, 0), 0xF0202020, 16.0, 0)
    current_text_y = score_board_y + 16
    current_text_x = score_board_x + 16
    idx = 0
    for val in player_list:
        if "img" in val:
            imgui.get_foreground_draw_list().add_image(val["img"].texture_handle, util.Vec3(current_text_x, current_text_y, 0), util.Vec3(current_text_x + 32, current_text_y + 32, 0), util.Vec3(0, 0, 0), util.Vec3(1, 1, 0), 0xE0E0E0FF)
        ping_txt = f" [{val.get('ping', 0)}ms]" if "ping" in val and val["ping"] >= 0 else ""
        imgui.get_foreground_draw_list().add_text(util.Vec3(current_text_x + 40, current_text_y, 0), 0xFFFFFFFF, val["name"] + ping_txt)
        idx += 1
        if idx == 12:
            break
        current_text_y += 40
        
    chat_width = 600
    chat_height = 400
    chat_x = totk.get_screen_width() - chat_width - 50
    chat_y = totk.get_screen_height() - chat_height - 50
    imgui.get_foreground_draw_list().add_rect_filled(util.Vec3(chat_x, chat_y, 0), util.Vec3(chat_x + chat_width, chat_y + chat_height, 0), 0xF0202020, 16.0, 0)
    idx = len(messages) - 1
    current_text_y = chat_y + chat_height - 32 - 16
    current_text_x = chat_x + 16
    drawn_count = 0
    while idx != -1:
        if len(messages) == idx:
            break
        msg = messages[idx]
        text = msg["name"] + ": " + msg["message"]
        while imgui.calc_text_size(text).x > chat_width * 2 - 100:
            text = text[:-1]
        imgui.get_foreground_draw_list().add_text(util.Vec3(current_text_x + 40, current_text_y, 0), 0xFFFFFFFF, text)
        for val in player_list:
            if val["uid"] != msg["source"]:
                continue
            if "img" in val:
                imgui.get_foreground_draw_list().add_image(val["img"].texture_handle, util.Vec3(current_text_x, current_text_y, 0), util.Vec3(current_text_x + 32, current_text_y + 32, 0), util.Vec3(0, 0, 0), util.Vec3(1, 1, 0), 0xE0E0E0FF)
        current_text_y -= 32
        idx -= 1
        drawn_count += 1
        if drawn_count == 12:
            break
    imgui.get_draw_list_shared_data().font_size = prev_font_size
    if not disable_font and amazing_font != None:
        imgui.pop_font()

def init():
    global player_list
    global messages
    global amazing_font
    global ui_enabled
    player_list = []
    messages = []
    amazing_font = None
    ui_enabled = False

    # Log available runtime APIs to server console
    try:
        api_info = f"TOTK_APIS: {', '.join([k for k in dir(totk) if not k.startswith('_')])}"
        util.send_event_to_server("com.kirbymimi.totk_plugins.client_chat", api_info)
    except Exception:
        pass

def receive_server_chat(obj):
    messages.append(obj)
    if len(messages) > 100:
        messages.pop(0)

util.register_event("calc", calc)
util.register_event("render", render)
util.register_event("com.kirbymimi.totk_plugins.client_list", update_client_list)
util.register_event("com.kirbymimi.totk_plugins.server_chat", receive_server_chat)
util.register_event("com.kirbymimi.totk_plugins.pong", on_pong)
util.register_event("init", init)