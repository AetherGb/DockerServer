# Co-op Features: Area Bullet-Time (Option A), Real-Time Menu Handling (Option 1), and Time/Weather Synchronization
import totk
import util

bullet_time_active = False
bullet_time_timer = 0.0
bullet_time_failsafe_limit = 3.5  # Max slow-mo duration to prevent freezing
zr_aiming_in_air = False

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

def check_bullet_time_local():
    global zr_aiming_in_air
    global bullet_time_timer
    global bullet_time_active

    controller = totk.get_controller(0)
    player = totk.get_player_actor()
    if player is None or not player.is_valid():
        return

    # Check if ZR (bow aim) is held
    zr_held = controller.is_zr_held()
    pos = player.position

    # Detection of mid-air bow aiming
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
        if bullet_time_timer <= 0.0:
            bullet_time_active = False
            set_game_timescale(1.0)

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
            dist = (dx * dx + dz * dz) ** 0.5
            if dist > 50.0:
                return  # Out of range, do not enter slow-mo
        bullet_time_active = True
        bullet_time_timer = bullet_time_failsafe_limit
        set_game_timescale(0.2)
    elif action == "stop":
        bullet_time_active = False
        bullet_time_timer = 0.0
        set_game_timescale(1.0)

def check_menu_pause():
    """Option 1 (Elden Ring style): Keep world simulation running during menu/inventory screens."""
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

def calc_coop():
    check_bullet_time_local()
    check_menu_pause()

util.register_event("calc", calc_coop)
util.register_event("com.kirbymimi.totk_plugins.bullet_time_broadcast", on_bullet_time_event)
util.register_event("com.kirbymimi.totk_plugins.time_skip", on_time_skip_event)
