class House:
    def __init__(self):
        self.aircon = False
        self.temperature = 24
        self.heater = False
        self.tv = False
        self.channel = 1
        self.volume = 10
        self.clean = True

    def turn_on_aircon(self):
        self.aircon = True
        print("에어컨을 켰습니다.")

    def turn_off_aircon(self):
        self.aircon = False
        print("에어컨을 껐습니다.")

    def set_temperature(self, temp):
        self.temperature = temp
        print(f"온도를 {temp}도로 설정했습니다.")

    def turn_on_heater(self):
        self.heater = True
        print("난방을 켰습니다.")

    def turn_off_heater(self):
        self.heater = False
        print("난방을 껐습니다.")

    def turn_on_tv(self):
        self.tv = True
        print("TV를 켰습니다.")

    def turn_off_tv(self):
        self.tv = False
        print("TV를 껐습니다.")

    def change_channel(self, channel):
        self.channel = channel
        print(f"{channel}번 채널로 변경했습니다.")

    def volume_up(self):
        self.volume += 1
        print(f"현재 볼륨 : {self.volume}")

    def volume_down(self):
        if self.volume > 0:
            self.volume -= 1
        print(f"현재 볼륨 : {self.volume}")

    def clean_room(self):
        self.clean = True
        print("방을 청소했다.")

    def make_dirty(self):
        self.clean = False
        print("방이 더러워졌다.")

    def show_status(self):
        print("===== 집 상태 =====")
        print(f"에어컨 : {'켜짐' if self.aircon else '꺼짐'}")
        print(f"온도 : {self.temperature}℃")
        print(f"난방 : {'켜짐' if self.heater else '꺼짐'}")
        print(f"TV : {'켜짐' if self.tv else '꺼짐'}")
        print(f"채널 : {self.channel}")
        print(f"볼륨 : {self.volume}")
        print(f"방 상태 : {'깨끗함' if self.clean else '더러움'}")

    def to_dict(self):
        return {
            "aircon": self.aircon,
            "temperature": self.temperature,
            "heater": self.heater,
            "tv": self.tv,
            "channel": self.channel,
            "volume": self.volume,
            "clean": self.clean,
        }


_shared_house = House()


def get_house_instance() -> House:
    return _shared_house


def reset_house_instance() -> House:
    global _shared_house
    _shared_house = House()
    return _shared_house
