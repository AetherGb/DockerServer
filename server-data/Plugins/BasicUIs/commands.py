# Console commands, invoked from the attached container console, e.g.:
#   list
#   broadcast Hello everyone
#   ban wesley
#   banip wesley
#   kick wesley
#   unban wesley
#   banned
#   save
#
# ban/banip/kick/unban accept either a nickname OR a save uid (shown by
# `list` and `banned`). Nicknames are NOT unique -- two different people
# (two different save UIDs) can have the same in-game name, and can even
# be on the same home network, so IP alone doesn't disambiguate them
# either. If a nickname matches more than one player/registered ban,
# nothing is guessed -- all matches are printed with their uid so the
# admin can re-run the command with the exact uid.
#
# ban vs banip -- there are two independent ban mechanisms now:
#   ban <player>    bans by save uid only. Blocks just that save file from
#                    reconnecting (under any name); does NOT affect anyone
#                    else on their network, including someone else with
#                    the same in-game name on the same connection. This is
#                    the one that actually solves the shared-network case.
#   banip <player>  bans by save uid AND IP, same as the original
#                    behavior. Use this when you deliberately want to
#                    block the whole network (repeat troublemakers coming
#                    back on new save files from the same house, etc).
# unban reverses whichever of the two were applied, based on what's
# recorded for that uid.
#
# teleport is implemented below but currently disabled (doesn't work yet --
# see the EXPERIMENTAL note on teleport()) -- its dispatch is commented out
# in console_command().
#
# Requires the CommandServer/PyDispatchCommand Java patch, which fires a
# "console_command" event for any console line that isn't an exact match
# for a built-in command like "py". This file registers a listener for
# that event. registered_clients and util come from server.py, since both
# files load into the same "BasicUIs" module and share one global scope.
#
# API notes (verified against the decompiled source):
#   util.ban_client(client) -> bans the client's IP via BanServer and
#       disconnects them. Requires an actual live ServerClient object, so
#       IP-banning only works on someone currently connected (inherent to
#       how BanServer.ban(InetAddress) works -- it needs their socket).
#   util.kick_client(client) -> just disconnects them, no ban.
#   util.get_server() -> the root Server actor, used to reach SaveServer.
#   client.getNickName() / getUID() (save uid) / getInstanceUID() (session id)
#   com.kirbymimi.serverCommon.ban.BanServer -- confirmed via BanServer.java.
#       Originally only had ban(InetAddress)/onClientConnect (IP check at
#       connect time). Added directly to that source:
#         unban(InetAddress) / isBanned(InetAddress)   -- IP, mirrors ban()
#         banUid(String) / unbanUid(String) / isUidBanned(String) -- new
#           parallel uid-based list, persisted the same way as the IP list.
#       The uid check itself is enforced in TOTKClient.java's
#       receiveClientInitPacket(), right after this.uid is parsed and
#       validated (confirmed via TOTKClient.java: getUID()/nickName are
#       both null until that handler runs, and it's the point where the
#       server first knows who's connecting -- BanServer's own
#       clientConnected/onClientConnect fires earlier, at raw socket
#       accept, before any uid exists, which is why the uid check couldn't
#       live there). All of this needs BanServer.class and TOTKClient.class
#       recompiled and rebuilt into server.jar/the image before ban/unban
#       below actually work on a given server -- until then the calls will
#       reach BanServer fine but fail since the methods don't exist yet.
#
# Since IP is fine but the ask is to ban/unban *by name*, ban_player()/
# ban_player_ip() write uid -> {name, ip, uid_banned, ip_banned, banned_at}
# to a small local JSON file (ban_registry.json, next to this script) at
# ban time, so unban_player() can look up what to reverse later. Only
# covers bans made after this change -- older bans (from before uid
# tracking existed) are kept under a synthetic "legacy:<name>" key so
# they're still findable by name, just IP-only with no real uid.

import java
import json
import os
import time

SaveServerClass = java.type("com.kirbymimi.totkServer.save.SaveServer")
BanServerClass = java.type("com.kirbymimi.serverCommon.ban.BanServer")
InetAddressClass = java.type("java.net.InetAddress")

# __file__ isn't defined here -- plugin scripts are handed to GraalVM's
# Python engine as a raw string via Context.eval(), never loaded as an
# actual file Source with a path (see PythonWrapper.createCode() in the
# decompiled server source), so there's no script-relative path to build
# from. docker-entrypoint.sh always `cd`s into the server's run directory
# before launching java, and this plugin always lives at Plugins/BasicUIs
# under that directory, so build the path from the process's cwd instead.
_BAN_REGISTRY_PATH = os.path.join(os.getcwd(), "Plugins", "BasicUIs", "ban_registry.json")


def _now_str():
    return time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime())


def _load_ban_registry():
    try:
        with open(_BAN_REGISTRY_PATH, "r") as f:
            raw = json.load(f)
    except Exception:
        return {}
    registry = {}
    changed = False
    for key, value in raw.items():
        if isinstance(value, dict):
            registry[key] = value
        else:
            # Pre-uid-tracking format was {name: ip}. No uid was ever
            # recorded for these, so keep them findable by name under a
            # synthetic key instead of dropping them.
            registry["legacy:" + key] = {"name": key, "ip": value, "banned_at": None}
            changed = True
    if changed:
        _save_ban_registry(registry)
    return registry


def _save_ban_registry(registry):
    try:
        with open(_BAN_REGISTRY_PATH, "w") as f:
            json.dump(registry, f)
    except Exception as e:
        print("Warning: couldn't persist ban registry: %s" % e)


def find_client(name):
    for client_data in registered_clients:
        c = client_data["server_client"]
        if c.getNickName() == name:
            return c
    return None


def _client_ip(c):
    try:
        return str(c.getSocket().getInetAddress().getHostAddress())
    except Exception:
        return None


def _resolve_online_client(identifier):
    """Resolve a console argument to exactly one online ServerClient.
    Accepts either a save uid (always unambiguous) or a nickname (only
    unambiguous if exactly one online player has it).

    Returns (client, matches): on a clean resolution `client` is set and
    `matches` is None; if a nickname matched more than one online player,
    `client` is None and `matches` is that list for the caller to print.
    """
    for client_data in registered_clients:
        c = client_data["server_client"]
        if str(c.getUID()) == identifier:
            return c, None

    matches = [cd["server_client"] for cd in registered_clients if cd["server_client"].getNickName() == identifier]
    if len(matches) == 1:
        return matches[0], None
    return None, matches


def _print_online_matches(identifier, matches):
    print("%d online players are named %s -- specify which one by save uid:" % (len(matches), identifier))
    for c in matches:
        print("  - uid=%s ip=%s" % (c.getUID(), _client_ip(c) or "unknown"))


def list_players():
    if not registered_clients:
        print("No players connected.")
        return
    for client_data in registered_clients:
        c = client_data["server_client"]
        print(" - %s (save uid=%s)" % (c.getNickName(), c.getUID()))


def broadcast(message):
    obj = {}
    obj["message"] = message
    obj["source"] = "SERVER"
    obj["name"] = "SERVER"
    util.send_event_to_all_clients("com.kirbymimi.totk_plugins.server_chat", obj)
    print("Broadcast sent: %s" % message)


def ban_player(identifier):
    """Ban by save uid only. Blocks this specific save file from
    reconnecting under any name, without touching their IP -- anyone else
    on the same network (even someone else with the same in-game name)
    can still connect. Use banip() instead to also block their network."""
    client, matches = _resolve_online_client(identifier)
    if client is None:
        if matches:
            _print_online_matches(identifier, matches)
        else:
            print("No online player named %s." % identifier)
        return

    uid = str(client.getUID())
    name = client.getNickName()

    ban_server = _find_ban_server()
    if ban_server is None:
        print("BanServer not found -- couldn't ban %s (uid=%s)." % (name, uid))
        return

    try:
        ban_server.banUid(uid)
    except Exception as e:
        print("banUid() call failed (%s) -- this server build may not have "
              "the patched BanServer yet." % e)
        return

    util.kick_client(client)

    registry = _load_ban_registry()
    entry = registry.get(uid, {})
    entry["name"] = name
    entry["uid_banned"] = True
    entry["banned_at"] = _now_str()
    registry[uid] = entry
    _save_ban_registry(registry)
    print("Banned %s (uid=%s) by save uid and disconnected them. Their "
          "network isn't blocked -- use 'banip %s' if you also want that."
          % (name, uid, identifier))


def ban_player_ip(identifier):
    """Ban by save uid AND IP -- also blocks anyone else on the same
    network. This is what the original ban command did."""
    client, matches = _resolve_online_client(identifier)
    if client is None:
        if matches:
            _print_online_matches(identifier, matches)
        else:
            print("No online player named %s. Banning their IP requires them "
                  "to be currently connected." % identifier)
        return

    uid = str(client.getUID())
    name = client.getNickName()
    ip = _client_ip(client)

    ban_server = _find_ban_server()
    if ban_server is not None:
        try:
            ban_server.banUid(uid)
        except Exception as e:
            print("(banUid() call failed: %s -- this server build may not "
                  "have the patched BanServer yet. Continuing with the IP "
                  "ban.)" % e)

    util.ban_client(client)  # bans the IP and disconnects them

    registry = _load_ban_registry()
    entry = registry.get(uid, {})
    entry["name"] = name
    entry["uid_banned"] = True
    entry["banned_at"] = _now_str()
    if ip:
        entry["ip"] = ip
    registry[uid] = entry
    _save_ban_registry(registry)

    if ip:
        print("Banned %s (uid=%s) by save uid AND IP (%s), and disconnected "
              "them. Anyone else on that network is blocked too until "
              "unbanned." % (name, uid, ip))
    else:
        print("Banned %s (uid=%s) by save uid and disconnected them, but "
              "couldn't record their IP -- their network wasn't blocked."
              % (name, uid))


def list_banned():
    registry = _load_ban_registry()
    if not registry:
        print("No recorded bans.")
        return
    for uid, entry in registry.items():
        print(" - %s (uid=%s ip=%s banned=%s)" % (
            entry.get("name", "?"), uid, entry.get("ip", "?"), entry.get("banned_at") or "unknown"
        ))


def _find_ban_server():
    try:
        return util.get_server().getChild(BanServerClass)
    except Exception:
        return None


def _do_unban(uid, entry, registry):
    name = entry.get("name", "?")
    ip = entry.get("ip")
    uid_banned = entry.get("uid_banned")
    ban_server = _find_ban_server()
    results = []

    if uid_banned:
        if ban_server is None:
            results.append("couldn't reach BanServer to lift the save-uid ban")
        else:
            try:
                removed = ban_server.unbanUid(uid)
                results.append("save-uid ban lifted" if removed else "save-uid wasn't actually in the ban list")
            except Exception as e:
                results.append("unbanUid() call failed (%s) -- server build may not have the patched BanServer yet" % e)

    if ip:
        if ban_server is None:
            results.append("couldn't reach BanServer to lift the IP ban")
        else:
            try:
                removed = ban_server.unban(InetAddressClass.getByName(ip))
                results.append(("IP %s ban lifted" % ip) if removed else ("IP %s wasn't actually in the ban list" % ip))
            except Exception as e:
                results.append("unban() call failed (%s) -- server build may not have the patched BanServer.unban() yet" % e)

    registry.pop(uid, None)
    _save_ban_registry(registry)
    if not results:
        results.append("no ban was recorded for this entry")
    print("Unban %s (uid=%s): %s." % (name, uid, "; ".join(results)))


def unban_player(identifier):
    registry = _load_ban_registry()

    if identifier in registry:
        _do_unban(identifier, registry[identifier], registry)
        return

    matches = [(uid, entry) for uid, entry in registry.items() if entry.get("name") == identifier]
    if not matches:
        print("No recorded ban for %s (by name or uid) -- they may not have "
              "been banned through this console, or the ban predates this "
              "feature." % identifier)
        return
    if len(matches) > 1:
        print("%d recorded bans are named %s -- specify which one by save uid:" % (len(matches), identifier))
        for uid, entry in matches:
            print("  - uid=%s ip=%s banned=%s" % (uid, entry.get("ip"), entry.get("banned_at") or "unknown"))
        return

    uid, entry = matches[0]
    _do_unban(uid, entry, registry)


def kick_player(identifier):
    client, matches = _resolve_online_client(identifier)
    if client is None:
        if matches:
            _print_online_matches(identifier, matches)
        else:
            print("No online player named %s." % identifier)
        return
    util.kick_client(client)
    print("Kicked %s (uid=%s)." % (client.getNickName(), client.getUID()))


def force_save():
    server = util.get_server()
    save_server = server.getChild(SaveServerClass)
    if save_server is None:
        print("SaveServer not found.")
        return
    save_server.save()
    print("Save triggered for the world and all connected players.")


def teleport(argline):
    parts = argline.split()
    if len(parts) < 2:
        print("Usage: teleport <player> <otherPlayer>  |  teleport <player> <x> <y> <z>")
        return
    src = find_client(parts[0])
    if src is None:
        print("No online player named %s." % parts[0])
        return
    src_uid = src.getInstanceUID()

    if len(parts) == 2:
        dest = find_client(parts[1])
        if dest is None:
            print("No online player named %s." % parts[1])
            return
        payload = {"target_uid": src_uid, "mode": "player", "dest_uid": dest.getInstanceUID()}
    elif len(parts) == 4:
        try:
            x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
        except ValueError:
            print("X, Y, Z must be numbers.")
            return
        payload = {"target_uid": src_uid, "mode": "coords", "x": x, "y": y, "z": z}
    else:
        print("Usage: teleport <player> <otherPlayer>  |  teleport <player> <x> <y> <z>")
        return

    # EXPERIMENTAL: relies on a matching handler in the client plugin (see
    # teleport_client.py) actually being able to move the player by setting
    # a synced actor's .position. That part is unverified -- see the notes
    # in teleport_client.py.
    util.send_event_to_all_clients("com.kirbymimi.totk_plugins.teleport", payload)
    print("Teleport request sent for %s." % parts[0])


def console_command(name, argline):
    argline = argline.strip() if argline else ""
    if name == "list":
        list_players()
    elif name == "broadcast":
        if argline:
            broadcast(argline)
        else:
            print("Usage: broadcast <message>")
    elif name == "ban":
        if argline:
            ban_player(argline.split()[0])
        else:
            print("Usage: ban <player>")
    elif name == "banip":
        if argline:
            ban_player_ip(argline.split()[0])
        else:
            print("Usage: banip <player>")
    elif name == "unban":
        if argline:
            unban_player(argline.split()[0])
        else:
            print("Usage: unban <player>")
    elif name == "banned":
        list_banned()
    elif name == "kick":
        if argline:
            kick_player(argline.split()[0])
        else:
            print("Usage: kick <player>")
    elif name == "save":
        force_save()
    # elif name == "teleport":
    #     teleport(argline)
    else:
        print("Unknown console command: %s (known: list, broadcast, ban, banip, unban, banned, kick, save)" % name)


util.register_event("console_command", console_command)
