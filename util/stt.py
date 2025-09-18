import os
import json
from typing import Any, Dict, Optional
from datetime import datetime, timezone, timedelta
import wave

import requests


class VitoSTTClient:
    """
    VITO STT API 클라이언트.

    - 인증 토큰 발급/재사용
    - 로컬 파일 전사 요청

    정책:
    - JWT 토큰은 환경변수를 사용하지 않습니다. 파일 기반으로 저장/재사용합니다.
    - client_id / client_secret은 생성자 인자 또는 환경변수(RTZR_CLIENT_ID, RTZR_CLIENT_SECRET)로 읽을 수 있습니다.
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        jwt_token: Optional[str] = None,
        base_url: str = "https://openapi.vito.ai/v1",
        request_timeout: int = 30,
        token_file: str = "vito_token.txt",
        token_ttl: timedelta = timedelta(hours=6),
    ) -> None:
        self.client_id = client_id or os.getenv("RTZR_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("RTZR_CLIENT_SECRET")
        # JWT 토큰은 환경변수에서 읽지 않습니다 (정책)
        self.jwt_token = jwt_token
        self.base_url = base_url.rstrip("/")
        self.request_timeout = request_timeout
        self.token_file = token_file
        self.token_ttl = token_ttl

    def authenticate(self) -> str:
        """
        클라이언트 자격증명으로 JWT 토큰을 발급받아 내부에 저장합니다.
        사전에 client_id/client_secret을 생성자나 환경변수로 제공해야 합니다.
        """
        if not self.client_id or not self.client_secret:
            raise ValueError(
                "Vito 인증 정보가 없습니다. client_id/client_secret을 전달하거나 환경변수 'RTZR_CLIENT_ID', 'RTZR_CLIENT_SECRET'을 설정하세요."
            )

        resp = requests.post(
            f"{self.base_url}/authenticate",
            data={"client_id": self.client_id, "client_secret": self.client_secret},
            timeout=self.request_timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        token = (
            data.get("access_token")
            or data.get("token")
            or data.get("jwt")
            or data.get("accessToken")
        )
        if not token:
            raise RuntimeError("인증 응답에서 토큰을 찾을 수 없습니다.")

        self.jwt_token = token
        return token

    def _ensure_token(self) -> None:
        if not self.jwt_token:
            # 파일에서 불러오거나 만료 시 재발급
            self.jwt_token = self.get_or_refresh_token()

    def _load_saved_token(self) -> tuple[Optional[str], Optional[datetime]]:
        """토큰 파일에서 토큰과 발급 시각을 읽습니다."""
        if not self.token_file or not os.path.isfile(self.token_file):
            return None, None
        try:
            with open(self.token_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            token = data.get("token")
            issued_at_str = data.get("issued_at")
            issued_at = (
                datetime.fromisoformat(issued_at_str)
                if isinstance(issued_at_str, str)
                else None
            )
            return token, issued_at
        except Exception:
            return None, None

    def _save_token(self, token: str, issued_at: datetime) -> None:
        """토큰과 발급 시각을 파일에 저장합니다."""
        payload = {
            "token": token,
            "issued_at": issued_at.replace(microsecond=0).isoformat(),
        }
        parent = os.path.dirname(self.token_file)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(self.token_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def get_or_refresh_token(self) -> str:
        """파일 기반 토큰을 로드하여 TTL이 지나면 재발급합니다."""
        saved_token, issued_at = self._load_saved_token()
        now = datetime.now(timezone.utc)

        if saved_token and issued_at:
            if issued_at.tzinfo is None:
                issued_at = issued_at.replace(tzinfo=timezone.utc)
            if now - issued_at < self.token_ttl:
                return saved_token

        # 재발급
        new_token = self.authenticate()
        self._save_token(new_token, now)
        return new_token

    def build_config(self, **overrides: Any) -> Dict[str, Any]:
        """
        기본 전사 설정을 생성합니다. 키워드 인자로 쉽게 덮어쓸 수 있습니다.

        예:
            build_config(use_diarization=False)
            build_config(diarization={"spk_count": 3})
        """
        config: Dict[str, Any] = {
            "use_diarization": True,
            "diarization": {"spk_count": 2},
            "use_itn": False,
            "use_disfluency_filter": False,
            "use_profanity_filter": False,
            "use_paragraph_splitter": True,
            "paragraph_splitter": {"max": 50},
        }

        for key, value in overrides.items():
            if key in {"diarization", "paragraph_splitter"} and isinstance(value, dict):
                config[key].update(value)
            else:
                config[key] = value

        return config

    def transcribe_file(
        self,
        file_path: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        로컬 오디오 파일을 업로드하여 전사합니다.

        Args:
            file_path: 오디오 파일 경로
            config: VITO 전사 설정 딕셔너리 (미제공 시 기본 설정 사용)

        Returns:
            전사 결과 JSON(dict)
        """
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")

        self._ensure_token()

        headers = {"Authorization": f"Bearer {self.jwt_token}"}
        payload = {"config": json.dumps(config or self.build_config(), ensure_ascii=False)}

        with open(file_path, "rb") as f:
            files = {"file": f}
            resp = requests.post(
                f"{self.base_url}/transcribe",
                headers=headers,
                data=payload,
                files=files,
                timeout=self.request_timeout,
            )
        resp.raise_for_status()
        return resp.json()

    def _try_fetch_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        작업 ID로 전사 결과를 조회합니다. 엔드포인트 차이를 감안해 2가지 경로를 시도합니다.
        성공 시 결과 JSON을 반환, 아직 준비 안 되었거나 404면 None.
        """
        headers = {"Authorization": f"Bearer {self.jwt_token}"}
        # 우선 /transcribe/{id}/result 시도
        for path in (f"/transcribe/{task_id}/result", f"/transcribe/{task_id}"):
            url = f"{self.base_url}{path}"
            try:
                r = requests.get(url, headers=headers, timeout=self.request_timeout)
                if r.status_code == 404:
                    continue
                r.raise_for_status()
                data = r.json()
                # 결과로 판단 가능한 키가 있으면 반환
                if isinstance(data, dict) and (
                    data.get("text")
                    or data.get("results")
                    or data.get("result")
                ):
                    return data
                # 일부 구현은 상태만 반환할 수 있음
                status = (data.get("status") or data.get("state") or "").lower()
                if status in {"completed", "done", "succeeded", "success"}:
                    return data
            except requests.HTTPError:
                continue
            except Exception:
                continue
        return None

    def transcribe_file_and_wait(
        self,
        file_path: str,
        config: Optional[Dict[str, Any]] = None,
        poll_interval_sec: float = 1.5,
        timeout_sec: float = 300.0,
    ) -> Dict[str, Any]:
        """
        파일 업로드 후 결과가 준비될 때까지 폴링하여 최종 전사 결과를 반환합니다.
        """
        initial = self.transcribe_file(file_path, config=config)

        # 업로드 응답에 바로 결과가 포함된 경우 처리
        if isinstance(initial, dict) and (
            initial.get("text") or initial.get("results") or initial.get("result")
        ):
            return initial

        task_id = None
        if isinstance(initial, dict):
            task_id = (
                initial.get("id")
                or initial.get("task_id")
                or initial.get("transcribe_id")
            )
        if not task_id:
            # 최후 수단: 그대로 반환 (상위에서 후처리하도록)
            return initial

        # 폴링
        import time as _time
        deadline = _time.time() + timeout_sec
        last_data: Optional[Dict[str, Any]] = None
        while _time.time() < deadline:
            self._ensure_token()
            data = self._try_fetch_result(task_id)
            if data is not None:
                # 완료 상태거나 결과 키가 존재하면 반환
                if (
                    data.get("text")
                    or data.get("results")
                    or data.get("result")
                ):
                    return data
                status = (data.get("status") or data.get("state") or "").lower()
                if status in {"completed", "done", "succeeded", "success"}:
                    return data
                last_data = data
            _time.sleep(poll_interval_sec)

        # 타임아웃: 마지막으로 본 데이터를 반환하거나 업로드 응답 반환
        return last_data or initial

    # ------------------------------
    # 녹음: 음성 → WAV 파일 저장
    # ------------------------------
    def record_to_wav(
        self,
        output_path: str,
        duration_sec: float = 5.0,
        samplerate: int = 16000,
        channels: int = 1,
    ) -> str:
        """
        pyaudio만 사용하여 고정 길이 녹음을 수행하고 WAV(PCM16, mono)로 저장합니다.
        """
        try:
            import pyaudio  # type: ignore

            pa = pyaudio.PyAudio()
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=samplerate,
                input=True,
                frames_per_buffer=1024,
            )
            frames: list[bytes] = []
            for _ in range(0, int(samplerate / 1024 * duration_sec)):
                frames.append(stream.read(1024))
            stream.stop_stream()
            stream.close()
            sampwidth = pa.get_sample_size(pyaudio.paInt16)
            pa.terminate()

            with wave.open(output_path, "wb") as wf:
                wf.setnchannels(channels)
                wf.setsampwidth(sampwidth)
                wf.setframerate(samplerate)
                wf.writeframes(b"".join(frames))

            return output_path
        except Exception as e:
            raise RuntimeError(
                "음성 녹음 실패: pyaudio가 필요합니다. 설치 예) pip install pyaudio"
            ) from e

    def record_until_silence(
        self,
        output_path: str,
        silence_seconds: float = 2.5,
        activation_threshold: Optional[int] = None,
        min_activation_threshold: int = 100,
        calibrate_seconds: float = 0.8,
        activation_boost: float = 1.2,
        samplerate: int = 16000,
        channels: int = 1,
        chunk_size: int = 1024,
        max_record_seconds: float = 60.0,
    ) -> str:
        """
        pyaudio만 사용하여 음성이 감지되면 녹음을 시작하고,
        지정한 무음 시간(silence_seconds) 동안 소리가 없으면 녹음을 중단하여 WAV로 저장합니다.
        - activation_threshold: 평균 절대 진폭 기준치 (int16 범위 기준, 0~32767)
        - max_record_seconds: 안전 장치(최대 녹음 시간)
        """
        try:
            import pyaudio  # type: ignore
            from array import array
            import time as _time

            pa = pyaudio.PyAudio()
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=samplerate,
                input=True,
                frames_per_buffer=chunk_size,
            )

            def _amp_level(data_bytes: bytes) -> int:
                samples = array("h")
                samples.frombytes(data_bytes)
                # 평균 절대값(간단한 energy proxy)
                total = 0
                for s in samples:
                    total += abs(s)
                return int(total / max(1, len(samples)))

            # 자동 임계치 보정 (환경이 조용할 때 약 0.8초 샘플)
            computed_threshold = activation_threshold
            if activation_threshold is None:
                calib_frames = max(1, int(samplerate / chunk_size * calibrate_seconds))
                levels = []
                for _ in range(calib_frames):
                    data0 = stream.read(chunk_size, exception_on_overflow=False)
                    levels.append(_amp_level(data0))
                if levels:
                    base = int(sum(levels) / len(levels))
                    computed_threshold = max(min_activation_threshold, int(base * activation_boost))
                else:
                    computed_threshold = min_activation_threshold

            threshold = int(computed_threshold if computed_threshold is not None else min_activation_threshold)

            recording = False
            frames: list[bytes] = []
            last_voice_time = None  # type: Optional[float]
            start_time = _time.time()
            # 지터 완화를 위한 지수평활
            ema_level = 0.0
            alpha = 0.3

            while True:
                data = stream.read(chunk_size, exception_on_overflow=False)
                level = _amp_level(data)
                ema_level = alpha * level + (1.0 - alpha) * ema_level

                if not recording:
                    # 대기: 음성 감지되면 녹음 시작
                    if ema_level >= threshold:
                        recording = True
                        last_voice_time = _time.time()
                        frames.append(data)
                else:
                    # 녹음 중: 프레임 축적, 소리 있으면 타임스탬프 갱신
                    frames.append(data)
                    if ema_level >= threshold:
                        last_voice_time = _time.time()

                    # 무음 지속 체크
                    if last_voice_time is not None and (_time.time() - last_voice_time) >= silence_seconds:
                        break

                # 최대 녹음 시간 제한
                if recording and (_time.time() - start_time) >= max_record_seconds:
                    break

            stream.stop_stream()
            stream.close()
            sampwidth = pa.get_sample_size(pyaudio.paInt16)
            pa.terminate()

            if not frames:
                # 음성 감지 못함
                raise RuntimeError("음성이 감지되지 않아 녹음을 종료했습니다.")

            with wave.open(output_path, "wb") as wf:
                wf.setnchannels(channels)
                wf.setsampwidth(sampwidth)
                wf.setframerate(samplerate)
                wf.writeframes(b"".join(frames))

            return output_path
        except Exception as e:
            raise RuntimeError(
                "음성 녹음 실패: pyaudio가 필요합니다. 설치 예) pip install pyaudio"
            ) from e


__all__ = ["VitoSTTClient"]


if __name__ == "__main__":
    # 예시 실행: client_id/client_secret은 생성자 인자 또는 환경변수(RTZR_CLIENT_ID, RTZR_CLIENT_SECRET)로 제공
    client = VitoSTTClient()
    try:
        # 필요한 시점에 토큰 확보/재발급 (파일 기반 관리)
        client.jwt_token = client.get_or_refresh_token()
        result = client.transcribe_file("sample.wav")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"오류: {e}")