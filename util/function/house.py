import json
from typing import Optional
from util.house import House, get_house_instance


def _get_house() -> House:
    return get_house_instance()


def get_house_status() -> str:
    return json.dumps(_get_house().to_dict(), ensure_ascii=False)


def turn_on_aircon() -> str:
    _get_house().turn_on_aircon()
    return get_house_status()


def turn_off_aircon() -> str:
    _get_house().turn_off_aircon()
    return get_house_status()


def set_temperature(temp: Optional[int] = None) -> str:
    if temp is None:
        return json.dumps({"status": "error", "message": "온도 값이 필요합니다."}, ensure_ascii=False)
    _get_house().set_temperature(int(temp))
    return get_house_status()


def turn_on_heater() -> str:
    _get_house().turn_on_heater()
    return get_house_status()


def turn_off_heater() -> str:
    _get_house().turn_off_heater()
    return get_house_status()


def turn_on_tv() -> str:
    _get_house().turn_on_tv()
    return get_house_status()


def turn_off_tv() -> str:
    _get_house().turn_off_tv()
    return get_house_status()


def change_channel(channel: Optional[int] = None) -> str:
    if channel is None:
        return json.dumps({"status": "error", "message": "채널 값이 필요합니다."}, ensure_ascii=False)
    _get_house().change_channel(int(channel))
    return get_house_status()


def volume_up() -> str:
    _get_house().volume_up()
    return get_house_status()


def volume_down() -> str:
    _get_house().volume_down()
    return get_house_status()


def clean_room() -> str:
    _get_house().clean_room()
    return get_house_status()


def make_dirty() -> str:
    _get_house().make_dirty()
    return get_house_status()


__all__ = [
    "turn_on_aircon",
    "turn_off_aircon",
    "set_temperature",
    "turn_on_heater",
    "turn_off_heater",
    "turn_on_tv",
    "turn_off_tv",
    "change_channel",
    "volume_up",
    "volume_down",
    "clean_room",
    "make_dirty",
    "get_house_status",
]
