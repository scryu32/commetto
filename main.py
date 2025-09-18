import os
import json
from datetime import datetime, timezone, timedelta
from openai import OpenAI
from util.tts import TTSService
from typing import Optional
import util
from util.stt import VitoSTTClient

# ------------------------------
# 기본 설정
# ------------------------------
GPT_MODEL = "gpt-4.1-nano"
client = OpenAI()
# 현재 대화의 저장 파일 경로 (콘솔 모드 등 모듈 수명 내에서 유지)
CURRENT_HISTORY_FILE: str | None = None

# 유저의 개인정보
user_information = {
    "name" : "유성찬",
    "namespace" : "scryu32",
    "email": "scryu32@gmail.com",
    "age" : "18",
    "birthday": "2008-09-19",
}

# prompt.txt 읽기
with open("prompt.txt", "r", encoding="utf-8") as f:
    base_prompt = f.read().strip()


def _load_all_memories(path: str = os.path.join("history", "memories.jsonl")) -> list[dict]:
    """
    저장된 모든 기억을 JSONL 파일에서 읽어 리스트로 반환합니다.
    파일이 없거나 파싱 실패한 라인은 건너뜁니다.
    """
    memories: list[dict] = []
    try:
        if not os.path.isfile(path):
            return memories
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        memories.append(obj)
                except Exception:
                    # 잘못된 라인은 무시
                    continue
    except Exception:
        # 읽기 실패 시 빈 목록 반환
        return []
    return memories


def _format_memories_for_system(memories: list[dict]) -> str:
    """
    시스템 프롬프트에 포함할 수 있도록 사람/모델 친화적으로 문자열 포맷팅합니다.
    """
    if not memories:
        return ""
    lines: list[str] = []
    for m in memories:
        description = m.get("description") if isinstance(m, dict) else None
        created_at = (m.get("created_at") if isinstance(m, dict) else None) or ""
        if description:
            if created_at:
                lines.append(f"- [{created_at}] {description}")
            else:
                lines.append(f"- {description}")
        else:
            # description 키가 없으면 전체를 문자열화
            try:
                lines.append(f"- {json.dumps(m, ensure_ascii=False)}")
            except Exception:
                lines.append(f"- {str(m)}")
    return "저장된 사용자 메모리:\n" + "\n".join(lines)


# system 메시지
_memories = _load_all_memories()
_memories_text = _format_memories_for_system(_memories)
system_content_parts = [
    base_prompt,
    f"유저의 개인정보: {user_information}, ",
]
if _memories_text:
    system_content_parts.append(_memories_text)
system_message = {"role": "system", "content": "\n".join(system_content_parts)}

# 툴 정의
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "특정 지역의 현재 날씨 정보를 가져옵니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "날씨를 알고 싶은 도시 이름 (예: 서울, 부산)"
                    }
                },
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "remember",
            "description": "사용자가 말한 내용, 취미, 특기 또는 사용자가 저장해달라고 요청한 정보를 기억해야 할 때 사용합니다. 사용자가 요청하지 않아도 특이 사항은 저장해야합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "기억할 정보의 내용을 작성해야합니다. \n 사용자가 자신의 소속, 꿈, 취미 등에 대해 말한 경우 바로바로 저장합니다. \n또한 사용자의 경험이나 변화에 대한 정보도 저장해야합니다."
                    }
                },
                "required": ["description"]
            }
        }
    },
]

# ------------------------------
# VITO JWT 토큰 관리 (파일 저장/재발급)
# ------------------------------
TOKEN_FILE = "vito_token.txt"
TOKEN_TTL = timedelta(hours=6)
CREDS_FILE = "vito_credentials.json"


def _load_saved_token() -> tuple[str | None, datetime | None]:
    """
    토큰 파일에서 토큰과 발급 시각을 읽어옵니다.
    파일이 없거나 파싱 실패 시 (None, None)을 반환합니다.
    """
    if not os.path.isfile(TOKEN_FILE):
        return None, None
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
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


def _save_token(token: str, issued_at: datetime) -> None:
    """토큰과 발급 시각을 파일에 저장합니다 (ISO8601)."""
    payload = {
        "token": token,
        "issued_at": issued_at.replace(microsecond=0).isoformat(),
    }
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def get_or_refresh_vito_token(client: VitoSTTClient) -> str:
    """
    저장된 토큰이 6시간 이내면 그대로 사용, 아니면 재발급 후 저장합니다.
    """
    saved_token, issued_at = _load_saved_token()
    now = datetime.now(timezone.utc)

    if saved_token and issued_at:
        # naive datetime이면 UTC로 간주하도록 보정
        if issued_at.tzinfo is None:
            issued_at = issued_at.replace(tzinfo=timezone.utc)
        if now - issued_at < TOKEN_TTL:
            return saved_token

    # 재발급
    new_token = client.authenticate()
    _save_token(new_token, now)
    return new_token


# ------------------------------
# STT 결과에서 텍스트 추출 유틸
# ------------------------------
def extract_transcript(stt_json: dict) -> str:
    """
    VITO 응답에서 사람이 말한 텍스트를 최대한 안전하게 추출합니다.
    불명확할 경우 전체 JSON을 문자열로 반환합니다.
    """
    if not isinstance(stt_json, dict):
        return str(stt_json)

    # 1) 가장 단순한 케이스: text
    if isinstance(stt_json.get("text"), str) and stt_json.get("text").strip():
        return stt_json["text"].strip()

    # 2) utterances 기반 결합 (자주 쓰이는 형태 가정)
    results = stt_json.get("results") or stt_json.get("result")
    if isinstance(results, dict):
        utterances = results.get("utterances") or results.get("segments")
        if isinstance(utterances, list):
            texts = []
            for u in utterances:
                if isinstance(u, dict):
                    # 후보 키들
                    for k in ("msg", "text", "transcript", "utterance"):
                        val = u.get(k)
                        if isinstance(val, str) and val.strip():
                            texts.append(val.strip())
                            break
            if texts:
                return " ".join(texts)

    # 3) 최후 수단: 전체 JSON 문자열
    try:
        return json.dumps(stt_json, ensure_ascii=False)
    except Exception:
        return str(stt_json)


# ------------------------------
# VITO 자격증명 로드/저장
# ------------------------------
def load_or_prompt_vito_credentials() -> tuple[str, str]:
    """
    자격증명을 파일에서 읽고, 없으면 사용자에게 입력받아 저장합니다.
    반환: (client_id, client_secret)
    """
    # 0) 환경변수 우선 사용
    env_cid = os.getenv("RTZR_CLIENT_ID")
    env_csec = os.getenv("RTZR_CLIENT_SECRET")
    if isinstance(env_cid, str) and isinstance(env_csec, str) and env_cid and env_csec:
        return env_cid, env_csec

    # 1) 저장 파일 존재 시 사용
    if os.path.isfile(CREDS_FILE):
        try:
            with open(CREDS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            cid = data.get("client_id")
            csec = data.get("client_secret")
            if isinstance(cid, str) and isinstance(csec, str) and cid and csec:
                return cid, csec
        except Exception:
            pass

    # 2) 마지막 수단: 사용자 입력 후 파일 저장
    print("VITO API 자격증명이 필요합니다. 한 번만 입력하면 파일에 저장됩니다.")
    cid = input(" - client_id: ").strip()
    csec = input(" - client_secret: ").strip()
    os.makedirs(os.path.dirname(CREDS_FILE) or ".", exist_ok=True)
    with open(CREDS_FILE, "w", encoding="utf-8") as f:
        json.dump({"client_id": cid, "client_secret": csec}, f, ensure_ascii=False, indent=2)
    return cid, csec

# ------------------------------
# GPT 대화 함수
# ------------------------------
def chat_with_gpt(user_input: str, messages: list, tts: Optional[TTSService] = None, use_tts: bool = False, append_user: bool = True) -> str:
    if append_user:
        messages.append({"role": "user", "content": user_input})

    # 1) 1차 응답: 스트리밍으로 받아서 화면에 즉시 출력
    stream = client.chat.completions.create(
        model=GPT_MODEL,
        messages=messages,
        tools=tools,
        stream=True
    )

    accumulated_content = ""
    tts_line_buffer = ""
    accumulated_tool_calls = []  # [{id, type, function: {name, arguments}}]
    saw_tool_calls = False

    for chunk in stream:
        choice = chunk.choices[0]
        delta = choice.delta

        # 일반 콘텐츠 스트리밍 출력
        if getattr(delta, "content", None):
            chunk_text = delta.content
            print(chunk_text, end="", flush=True)
            accumulated_content += chunk_text
            if use_tts and tts is not None:
                # 줄바꿈 단위로 분리하여 완료된 줄만 즉시 요청
                tts_line_buffer += chunk_text
                parts = tts_line_buffer.split("\n")
                completed_lines = parts[:-1]
                tts_line_buffer = parts[-1]
                for line in completed_lines:
                    line = line.strip()
                    if line:
                        tts.speak(line)

        # 함수 호출(툴콜) 누적 수집
        tool_calls_delta = getattr(delta, "tool_calls", None)
        if tool_calls_delta:
            saw_tool_calls = True
            for tc in tool_calls_delta:
                index = getattr(tc, "index", 0) or 0
                while len(accumulated_tool_calls) <= index:
                    accumulated_tool_calls.append({
                        "id": None,
                        "type": "function",
                        "function": {"name": "", "arguments": ""}
                    })

                entry = accumulated_tool_calls[index]
                if getattr(tc, "id", None):
                    entry["id"] = tc.id

                if getattr(tc, "function", None):
                    if getattr(tc.function, "name", None):
                        # name은 보통 한 번만 옴. 중복 오면 이어붙여도 무해
                        entry["function"]["name"] += tc.function.name
                    if getattr(tc.function, "arguments", None):
                        entry["function"]["arguments"] += tc.function.arguments

    # 스트림 종료 후 처리
    if saw_tool_calls:
        # 어시스턴트의 툴콜 메시지 기록
        assistant_tool_msg = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tc.get("id"),
                    "type": "function",
                    "function": {
                        "name": tc["function"]["name"],
                        "arguments": tc["function"]["arguments"]
                    }
                }
                for tc in accumulated_tool_calls
            ]
        }
        messages.append(assistant_tool_msg)

        # 각 툴콜 실행 및 도구 메시지 추가
        import json as _json
        for tc in accumulated_tool_calls:
            func_name = tc["function"]["name"]
            raw_args = tc["function"]["arguments"] or "{}"
            try:
                parsed_args = _json.loads(raw_args)
            except Exception:
                parsed_args = {}

            if func_name == "get_weather":
                location = parsed_args.get("location")
                result = util.get_weather(location)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id"),
                    "content": result
                })

            elif func_name == "remember":
                description = parsed_args.get("description")
                try:
                    result = util.remember(description)
                except Exception as e:
                    # 함수 호출 실패 시에도 GPT가 맥락상 답변하도록 에러를 JSON으로 넘김
                    result = _json.dumps({"status": "error", "message": str(e) }, ensure_ascii=False)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id"),
                    "content": result
                })

        # 2) 툴 결과 반영한 최종 답변 스트리밍
        final_stream = client.chat.completions.create(
            model=GPT_MODEL,
            messages=messages,
            tools=tools,
            stream=True
        )

        final_content = ""
        tts_line_buffer = ""
        for chunk in final_stream:
            choice = chunk.choices[0]
            delta = choice.delta
            if getattr(delta, "content", None):
                chunk_text = delta.content
                print(chunk_text, end="", flush=True)
                final_content += chunk_text
                if use_tts and tts is not None:
                    tts_line_buffer += chunk_text
                    parts = tts_line_buffer.split("\n")
                    completed_lines = parts[:-1]
                    tts_line_buffer = parts[-1]
                    for line in completed_lines:
                        line = line.strip()
                        if line:
                            tts.speak(line)

        # 스트림 종료 후 남은 버퍼 처리(마지막 줄)
        if use_tts and tts is not None:
            leftover = tts_line_buffer.strip()
            if leftover:
                tts.speak(leftover)

        messages.append({"role": "assistant", "content": final_content})
        try:
            save_history(messages)
        except Exception:
            pass
        return final_content

    # 툴콜이 없는 일반 답변의 경우: 이미 화면에 출력했으므로 대화 기록만 남김
    messages.append({"role": "assistant", "content": accumulated_content})
    # 1단계 스트림 종료 시 남은 버퍼 처리(툴콜이 없는 경우)
    if use_tts and tts is not None:
        leftover = tts_line_buffer.strip()
        if leftover:
            tts.speak(leftover)
    try:
        save_history(messages)
    except Exception:
        pass
    return accumulated_content

# ------------------------------
# 대화 저장 함수 (JSON 형식)
# ------------------------------
def _generate_history_filename(messages: list) -> str:
    """대화 파일명을 생성합니다 (타임스탬프 + 첫 사용자 메시지 앞부분)."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    first_user_msg = ""
    for msg in messages:
        if msg.get("role") == "user":
            first_user_msg = msg.get("content", "").strip().replace(" ", "_")
            first_user_msg = "".join(c for c in first_user_msg if c.isalnum() or c in "_-")
            first_user_msg = first_user_msg[:10]
            break
    if first_user_msg:
        return os.path.join("history", f"{timestamp}_{first_user_msg}.json")
    return os.path.join("history", f"{timestamp}.json")


def save_history(messages: list):
    """대화 저장: 처음 호출 시 파일을 생성하고, 이후 같은 파일에 덮어씁니다.

    우선순위:
    1) 환경변수 HOSHIP_HISTORY_FILE 지정 시 해당 경로 사용 (Streamlit 세션용)
    2) 모듈 전역 CURRENT_HISTORY_FILE 있으면 사용 (콘솔 모드 지속)
    3) 없으면 새 파일명 생성 후 전역에 저장
    """
    os.makedirs("history", exist_ok=True)

    # 1) 환경변수 우선
    env_path = os.getenv("HOSHIP_HISTORY_FILE")
    if isinstance(env_path, str) and env_path.strip():
        filename = env_path
        os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)
    else:
        # 2) 전역 또는 새 파일 생성
        global CURRENT_HISTORY_FILE
        if not CURRENT_HISTORY_FILE:
            CURRENT_HISTORY_FILE = _generate_history_filename(messages)
        filename = CURRENT_HISTORY_FILE

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)
    print(f"\n💾 대화 내역 저장 완료(JSON): {filename}")

# ------------------------------
# 메인 루프
# ------------------------------
if __name__ == "__main__":
    messages = [system_message]

    try:
        # VITO 자격증명 로드 또는 입력
        _client_id, _client_secret = load_or_prompt_vito_credentials()
        # VITO 토큰 확보/재발급 및 저장
        vito_client = VitoSTTClient(client_id=_client_id, client_secret=_client_secret)
        jwt_token = get_or_refresh_vito_token(vito_client)
        # 읽어온 토큰으로 클라이언트 동기화
        vito_client.jwt_token = jwt_token

        # 모드 선택: STT 여부
        mode_answer = input("🎙️ 음성(STT) 모드로 진행할까요? (y/N): ").strip().lower()
        use_stt = mode_answer in ("y", "yes", "ㅇ", "ㅇㅇ")

        # 모드 선택: TTS 여부
        tts_answer = input("🔊 음성 출력(TTS) 모드로 진행할까요? (y/N): ").strip().lower()
        use_tts = tts_answer in ("y", "yes", "ㅇ", "ㅇㅇ")

        tts_service: TTSService | None = None
        if use_tts:
            project_dir = os.path.dirname(os.path.abspath(__file__))
            tts_service = TTSService(dir_path=project_dir)
            tts_service.start()

        while True:
            if use_stt:
                # STT 모드: 음성 감지 → 무음 2.5초 시 종료 → 저장 → 전사 → 텍스트 → GPT
                wav_path = os.path.join("history_wav", f"record_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav")
                os.makedirs(os.path.dirname(wav_path), exist_ok=True)

                print("🎙️ 말하기 시작하세요. (무음 2초 지속 시 자동 종료)")

                try:
                    # 사용자가 말하기 시작하므로, 재생/대기 중인 TTS 중단
                    if use_tts and tts_service is not None:
                        tts_service.stop_all()
                    vito_client.record_until_silence(
                        wav_path,
                        silence_seconds=2,
                    )
                    print(f"💾 저장됨: {wav_path}")
                except Exception as e:
                    print(f"⚠️  녹음 실패: {e}")
                    continue

                # 토큰 최신화 (6시간 TTL)
                vito_client.jwt_token = get_or_refresh_vito_token(vito_client)

                try:
                    stt_json = vito_client.transcribe_file_and_wait(wav_path)
                    user_input = extract_transcript(stt_json)
                    print(f"👤 사용자(STT): {user_input}")
                except Exception as e:
                    print(f"⚠️  STT 실패: {e}")
                    continue
            else:
                user_input = input("👤 사용자: ")
                if user_input.lower() in ["exit", "quit", "종료"]:
                    break
                # 텍스트 입력이 도착했으므로 TTS 즉시 중단
                if use_tts and tts_service is not None:
                    tts_service.stop_all()

            # 스트리밍 출력: 프리픽스만 먼저 출력하고, 함수 내부에서 토큰 단위 출력
            print("🤖 GPT: ", end="", flush=True)
            assistant_output = chat_with_gpt(user_input, messages, tts=tts_service, use_tts=use_tts)
            print()  # 줄바꿈

    except KeyboardInterrupt:
        print("\n⚠️  Ctrl + C 감지: 프로그램 종료")

    finally:
        try:
            save_history(messages)
        finally:
            # TTS 정리
            try:
                if 'tts_service' in locals() and tts_service is not None:
                    tts_service.shutdown()
            except Exception:
                pass
