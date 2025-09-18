import requests
import struct
import os
import uuid
import threading
import queue
import wave
from typing import Optional

class TTSService:
    def __init__(self, dir_path: str):
        self.dir = dir_path
        # 큐: 텍스트 → 합성 파일 경로
        self._text_queue: "queue.Queue[str]" = queue.Queue()
        self._audio_queue: "queue.Queue[str]" = queue.Queue()

        # 워커 스레드
        self._synth_worker: Optional[threading.Thread] = None
        self._play_worker: Optional[threading.Thread] = None

        # 제어 이벤트
        self._shutdown = threading.Event()
        self._cancel_current = threading.Event()

    # ------------------------------
    # 외부 API
    # ------------------------------
    def start(self) -> None:
        if self._synth_worker and self._synth_worker.is_alive() and self._play_worker and self._play_worker.is_alive():
            return
        self._shutdown.clear()
        self._synth_worker = threading.Thread(target=self._run_synth_worker, name="TTSSynthWorker", daemon=True)
        self._play_worker = threading.Thread(target=self._run_play_worker, name="TTSPlayWorker", daemon=True)
        self._synth_worker.start()
        self._play_worker.start()

    def speak(self, text: str) -> None:
        if not isinstance(text, str):
            return
        text = text.strip()
        if not text:
            return
        self._text_queue.put(text)

    def stop_all(self) -> None:
        # 현재 재생/요청 중단 신호
        self._cancel_current.set()
        # 대기 중인 큐 비우기 (텍스트/오디오 모두)
        try:
            while True:
                self._text_queue.get_nowait()
        except queue.Empty:
            pass
        try:
            while True:
                path = self._audio_queue.get_nowait()
                try:
                    if os.path.isfile(path):
                        os.remove(path)
                except Exception:
                    pass
        except queue.Empty:
            pass
        # 이후 새 요청을 받을 수 있도록 즉시 해제
        self._cancel_current.clear()

    def shutdown(self) -> None:
        # 모든 작업 중단 및 종료
        self._cancel_current.set()
        self._shutdown.set()
        if self._synth_worker:
            self._synth_worker.join(timeout=2.0)
            self._synth_worker = None
        if self._play_worker:
            self._play_worker.join(timeout=2.0)
            self._play_worker = None
        self._cancel_current.clear()

    # ------------------------------
    # 내부 동작
    # ------------------------------
    def _run_synth_worker(self) -> None:
        while not self._shutdown.is_set():
            try:
                text = self._text_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if self._shutdown.is_set():
                break

            wav_path = self._text_to_speech_file(text, stop_event=self._cancel_current)
            if self._cancel_current.is_set() or not wav_path:
                # 취소 또는 실패 시 파일 정리
                if wav_path and os.path.isfile(wav_path):
                    try:
                        os.remove(wav_path)
                    except Exception:
                        pass
                continue

            # 합성 성공: 재생 큐에 추가
            self._audio_queue.put(wav_path)

    def _run_play_worker(self) -> None:
        while not self._shutdown.is_set():
            try:
                wav_path = self._audio_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if self._shutdown.is_set():
                break

            try:
                self._play_wav_blocking(wav_path, stop_event=self._cancel_current)
            finally:
                try:
                    if os.path.isfile(wav_path):
                        os.remove(wav_path)
                except Exception:
                    pass

    def _text_to_speech_file(self, text: str, stop_event: Optional[threading.Event] = None) -> Optional[str]:
        url = "http://127.0.0.1:9880/tts"
        payload = {
            "text": text,
            "text_lang": "ko",
            "ref_audio_path": f"{self.dir}\\example_wavs\\example.wav",
            "aux_ref_audio_path": [f"{self.dir}\\example_wavs\\{i}_audio.wav" for i in range(11)],
            "prompt_text": "",
            "prompt_lang": "ko",
            "text_split_method": "cut5",
            "batch_size": 1,
            "media_type": "wav",
            "streaming_mode": "true"
        }

        try:
            with requests.get(url, params=payload, stream=True, timeout=30) as response:
                response.raise_for_status()

                audio_data = b""
                for chunk in response.iter_content(chunk_size=8192):
                    if stop_event is not None and stop_event.is_set():
                        return None
                    if chunk:
                        audio_data += chunk

            total_size = len(audio_data)
            data_size = total_size - 44

            if total_size >= 44:
                audio_data = audio_data[:4] + struct.pack('<I', total_size - 8) + audio_data[8:]
                audio_data = audio_data[:40] + struct.pack('<I', data_size) + audio_data[44:]

            output_path = f"temp_audio/{uuid.uuid4().hex}.wav"
            os.makedirs("temp_audio", exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(audio_data)

            return output_path

        except Exception as e:
            print(f"⚠️ 예외 발생: {e}")
            return None

    def _play_wav_blocking(self, wav_path: str, stop_event: Optional[threading.Event] = None) -> None:
        """pyaudio가 있으면 스트리밍 재생(중단 가능), 없으면 wave+winsound 동기 재생"""
        try:
            import pyaudio  # type: ignore
        except Exception:
            pyaudio = None  # type: ignore

        if pyaudio is not None:
            try:
                import pyaudio  # type: ignore
                wf = wave.open(wav_path, 'rb')
                pa = pyaudio.PyAudio()
                stream = pa.open(format=pa.get_format_from_width(wf.getsampwidth()),
                                 channels=wf.getnchannels(),
                                 rate=wf.getframerate(),
                                 output=True)
                chunk = 1024
                data = wf.readframes(chunk)
                while data:
                    if stop_event is not None and stop_event.is_set():
                        break
                    stream.write(data)
                    data = wf.readframes(chunk)
                stream.stop_stream()
                stream.close()
                pa.terminate()
                wf.close()
                return
            except Exception as e:
                print(f"⚠️ 재생 실패(pyaudio): {e}")

        # Fallback: winsound (Windows 전용, 중단 제어 제한)
        try:
            import winsound  # type: ignore
            # 동기 재생: stop_event으로 즉시 중단은 어려움
            winsound.PlaySound(wav_path, winsound.SND_FILENAME)
        except Exception as e:
            print(f"⚠️ 재생 실패(fallback): {e}")
