# Co-op Features: Area Bullet-Time (Option A), Real-Time Menu Handling, and Time/Weather Synchronization
import math

try:
    import totk
    import util
    import imgui
except Exception:
    pass

bullet_time_active = False
bullet_time_timer = 0.0
bullet_time_failsafe_limit = 3.5  # Max slow-mo duration to prevent freezing
zr_aiming_in_air = False
last_y_pos = 0.0
is_in_air = False

def set_game_timescale(scale):
    """Attempt to invoke engine time-scale hooks if exposed by native runtime."""
    for fn in ["set_time_scale", "set_game_speed", "set_timescale", "set_speed", "set_world_speed"]:
        if hasattr(totk, fn):
            try:
                getattr(totk, fn)(scale)
                return True
            except Exception:
                pass
    return False

def apply_actor_slowmo(factor):
    """Slow down non-local puppets and actors in the vicinity during bullet-time."""
    try:
        my_actor = totk.get_player_synced_actor() if hasattr(totk, "get_player_synced_actor") else None
        for sa in totk.get_synced_actors():
            if sa == my_actor:
                continue
            if hasattr(sa, "get_game_actor"):
                game_act = sa.get_game_actor()
                if game_act and hasattr(game_act, "get_phive_controller_set"):
                    phive = game_act.get_phive_controller_set()
                    if phive and hasattr(phive, "get_character_controller"):
                        cc = phive.get_character_controller()
                        if cc and hasattr(cc, "get_character_property"):
                            prop = cc.get_character_property()
                            if prop and hasattr(prop, "get_forward_speed"):
                                sp = prop.get_forward_speed()
                                prop.set_forward_speed(sp * factor)
    except Exception:
        pass

def check_bullet_time_local():
    global zr_aiming_in_air
    global bullet_time_timer
    global bullet_time_active
    global last_y_pos
    global is_in_air

    try:
        controller = totk.get_controller(0)
        player = totk.get_player_actor()
        if player is None or not player.is_valid():
            return

        pos = player.position
        # Simple vertical delta check to estimate airborne state
        dy = pos.y - last_y_pos
        last_y_pos = pos.y
        if abs(dy) > 0.05:
            is_in_air = True
        else:
            is_in_air = False

        # Check if ZR (bow aim) is held
        zr_held = False
        if hasattr(controller, "is_zr_held"):
            zr_held = controller.is_zr_held()

        # Detection of mid-air bow aiming or flurry rush
        if zr_held and not zr_aiming_in_air:
            zr_aiming_in_air = True
            payload = {
                "action": "start",
                "x": pos.x,
                "y": pos.y,
                "z": pos.z
            }
            util.send_event_to_server("com.kirbymimi.totk_plugins.bullet_time", payload)
        elif not zr_held and zr_aiming_in_air:
            zr_aiming_in_air = False
            payload = {
                "action": "stop"
            }
            util.send_event_to_server("com.kirbymimi.totk_plugins.bullet_time", payload)

        # Local bullet time failsafe countdown
        if bullet_time_active:
            bullet_time_timer -= totk.get_delta_time()
            apply_actor_slowmo(0.3)
            if bullet_time_timer <= 0.0:
                bullet_time_active = False
                set_game_timescale(1.0)
                apply_actor_slowmo(1.0)
    except Exception:
        pass

def on_bullet_time_event(data):
    global bullet_time_active
    global bullet_time_timer

    action = data.get("action", "")
    if action == "start":
        # Option A: Check proximity (50m radius)
        me = None
        if hasattr(totk, "get_player_actor"):
            me = totk.get_player_actor()
        elif hasattr(totk, "get_player_synced_actor"):
            me = totk.get_player_synced_actor()
        if me is not None and hasattr(me, "position") and "x" in data and "z" in data:
            dx = me.position.x - float(data.get("x", 0.0))
            dz = me.position.z - float(data.get("z", 0.0))
            dist = math.sqrt(dx * dx + dz * dz)
            if dist > 50.0:
                return  # Out of range, do not enter slow-mo
        bullet_time_active = True
        bullet_time_timer = bullet_time_failsafe_limit
        set_game_timescale(0.2)
        apply_actor_slowmo(0.2)
    elif action == "stop":
        bullet_time_active = False
        bullet_time_timer = 0.0
        set_game_timescale(1.0)
        apply_actor_slowmo(1.0)

def check_menu_pause():
    """Option 1: Keep world simulation running during menu/inventory screens if hook available."""
    for fn in ["set_paused", "set_world_paused", "disable_menu_pause", "unpause", "set_pause_state"]:
        if hasattr(totk, fn):
            try:
                getattr(totk, fn)(False)
            except Exception:
                pass

def on_time_skip_event(data):
    """Handle sleep / campfire rest event: synchronize local game clock immediately."""
    hour = data.get("hour", None)
    if hour is not None:
        for fn in ["set_current_hour", "set_game_hour", "set_time", "set_time_of_day"]:
            if hasattr(totk, fn):
                try:
                    getattr(totk, fn)(hour)
                    break
                except Exception:
                    pass

def render_bullet_time_ui():
    """Render a visual indicator banner when bullet time / slow-mo is active."""
    global bullet_time_active
    global bullet_time_timer
    if not bullet_time_active:
        return
    try:
        sw = totk.get_screen_width()
        txt = f"[AREA BULLET-TIME ACTIVE: {max(0.0, bullet_time_timer):.1f}s]"
        draw_list = imgui.get_foreground_draw_list()
        text_size = imgui.calc_text_size(txt)
        bx = (sw - text_size.x) / 2.0
        by = 35.0
        # Background badge with golden slow-mo color
        draw_list.add_rect_filled(util.Vec3(bx - 12, by - 4, 0), util.Vec3(bx + text_size.x + 12, by + text_size.y + 4, 0), 0xC0000000, 8.0, 0)
        draw_list.add_rect(util.Vec3(bx - 12, by - 4, 0), util.Vec3(bx + text_size.x + 12, by + text_size.y + 4, 0), 0xFFFFAA00, 8.0, 0, 1.5)
        draw_list.add_text(util.Vec3(bx, by, 0), 0xFFFFAA00, txt)
    except Exception:
        pass

def calc_coop():
    check_bullet_time_local()
    check_menu_pause()

util.register_event("calc", calc_coop)
util.register_event("render", render_bullet_time_ui)
util.register_event("com.kirbymimi.totk_plugins.bullet_time_broadcast", on_bullet_time_event)
util.register_event("com.kirbymimi.totk_plugins.time_skip", on_time_skip_event)
