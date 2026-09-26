# EXPERIMENTAL -- unverified.
#
# I could confirm from client.py that these exist and are readable:
#   totk.get_player_synced_actor()  -> your own local player's synced actor
#   totk.get_synced_actors()        -> all synced actors (other players)
#   synced_actor.position           -> a Vec3, read here in client.py already
#   synced_actor.player_instance_uid
#
# What I could NOT confirm: whether `.position` can be *assigned* to, and
# whether doing so actually moves your character properly (updates physics/
# collision/camera) versus just being a read-only mirror value used for
# rendering other players' minimap icons. These bindings are native
# engine bindings outside the Java source I have access to, so this is a
# best-effort attempt built from the visible API surface, not something
# I've been able to test.
#
# Test carefully -- ideally on a save/character you don't mind risking --
# before relying on this. If assigning .position does nothing or errors,
# that confirms it's read-only and this approach needs a different API
# (or isn't possible without a proper "warp" call the engine doesn't
# expose to plugins).

import totk
import util

def on_teleport(data):
    me = totk.get_player_synced_actor()
    if me is None:
        return
    if me.player_instance_uid != data["target_uid"]:
        return  # this teleport request isn't for us

    if data["mode"] == "coords":
        me.position = util.Vec3(data["x"], data["y"], data["z"])
    elif data["mode"] == "player":
        for synced_actor in totk.get_synced_actors():
            if synced_actor.player_instance_uid == data["dest_uid"]:
                me.position = synced_actor.position
                break

util.register_event("com.kirbymimi.totk_plugins.teleport", on_teleport)
