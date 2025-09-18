import os
from datetime import datetime
import streamlit as st
import streamlit.components.v1 as components
import html
from util.stt import VitoSTTClient
from util.tts import TTSService
from main import (
    system_message,
    chat_with_gpt,
    save_history,
    extract_transcript,
    get_or_refresh_vito_token,
    load_or_prompt_vito_credentials,
)


st.set_page_config(page_title="Commetto - Chat", page_icon="🌟", layout="wide")

# 기존 디자인 제목
st.title("🌟 Commetto Chat")

# 환경변수에 API Key가 없으면 중단
if not os.getenv("OPENAI_API_KEY"):
    st.error("환경변수 OPENAI_API_KEY가 설정되지 않았습니다.")
    st.stop()

# 세션 상태 초기화
if "messages" not in st.session_state:
    st.session_state.messages = [system_message]
if "use_tts" not in st.session_state:
    st.session_state.use_tts = False
if "tts_service" not in st.session_state:
    st.session_state.tts_service = None
if "use_stt" not in st.session_state:
    st.session_state.use_stt = False
if "stt_client" not in st.session_state:
    st.session_state.stt_client = None
if "last_message_count" not in st.session_state:
    st.session_state.last_message_count = 0

col1, col2 = st.columns([3, 2], gap="large")

with col1:
    # 메시지 전용 스크롤 박스 렌더링 (system 제외)
    items = []
    for msg in st.session_state.messages[1:]:
        role = msg.get("role")
        content = msg.get("content")
        if not content:
            continue
        if role not in ("user", "assistant"):
            continue
        safe = html.escape(str(content))
        cls = "user" if role == "user" else "assistant"
        items.append(f'<div class="msg {cls}"><div class="bubble">{safe}</div></div>')

    chat_html = """
<style>
.chat-box { height: 560px; overflow-y: auto; padding: 8px 0; }
.msg { display: flex; margin: 6px 0; }
.msg.user { justify-content: flex-end; }
.msg.assistant { justify-content: flex-start; margin-bottom: 15px; }
.bubble { max-width: 85%; padding: 10px 12px; border-radius: 12px; white-space: pre-wrap; word-break: break-word; }
.msg.user .bubble { background: #DCF2FF; color: #000; }
.msg.assistant .bubble { background: #F2F2F2; color: #000; }
</style>
<div id="chat-box" class="chat-box">{items}</div>
<script>
  try {
    const box = document.getElementById('chat-box');
    if (box) { box.scrollTop = box.scrollHeight; }
  } catch (e) {}
</script>
""".replace("{items}", "".join(items))

    components.html(chat_html, height=560, scrolling=False)

    # 새 메시지 카운터 갱신 (자동 스크롤은 위 chat-box 스크립트가 처리)
    if st.session_state.last_message_count != len(st.session_state.messages):
        st.session_state.last_message_count = len(st.session_state.messages)

    # 입력창(메시지 박스 아래 배치) 및 전사 텍스트 전송 버튼
    # Streamlit 세션마다 고유 파일로 저장하려면 환경변수로 파일 경로를 지정
    if "history_file_initialized" not in st.session_state:
        import uuid
        os.makedirs("history", exist_ok=True)
        st.session_state["history_file_initialized"] = True
        st.session_state["history_file_path"] = os.path.join("history", f"session_{uuid.uuid4().hex[:8]}.json")
        os.environ["HOSHIP_HISTORY_FILE"] = st.session_state["history_file_path"]

    with st.form("chat_form", clear_on_submit=True):
        user_text = st.text_input("메시지를 입력하세요…", key="chat_text_input", label_visibility="collapsed", autocomplete="off")
        submitted = st.form_submit_button("보내기")

    if submitted and user_text.strip():
        # 1) 사용자 메시지를 즉시 세션에 반영 (UI 즉시 업데이트)
        timestamp_str = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        st.session_state.messages.append({"role": "system", "content": f"현재 시각:{timestamp_str}"})
        st.session_state.messages.append({"role": "user", "content": user_text})

        # 2) AI 응답 생성 (중복 방지: append_user=False)
        try:
            reply = chat_with_gpt(
                user_text,
                st.session_state.messages,
                tts=st.session_state.tts_service,
                use_tts=st.session_state.use_tts,
                append_user=False,
            )
        except Exception as e:
            st.error(f"응답 생성 실패: {e}")
        else:
            try:
                if hasattr(st, "rerun"):
                    st.rerun()
                else:
                    st.experimental_rerun()  # type: ignore[attr-defined]
            except Exception:
                pass

    if "transcript_area" in st.session_state and st.session_state.get("transcript_area"):
        if st.button("전사 텍스트로 보내기"):
            text_to_send = st.session_state.get("transcript_area", "").strip()
            if text_to_send:
                # 사용자 메시지를 먼저 반영
                timestamp_str = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
                st.session_state.messages.append({"role": "system", "content": f"현재 시각:{timestamp_str}"})
                st.session_state.messages.append({"role": "user", "content": text_to_send})
                try:
                    reply = chat_with_gpt(
                        text_to_send,
                        st.session_state.messages,
                        tts=st.session_state.tts_service,
                        use_tts=st.session_state.use_tts,
                        append_user=False,
                    )
                except Exception as e:
                    st.error(f"응답 생성 실패: {e}")
                else:
                    try:
                        if hasattr(st, "rerun"):
                            st.rerun()
                        else:
                            st.experimental_rerun()  # type: ignore[attr-defined]
                    except Exception:
                        pass

    # 저장 버튼은 오른쪽 패널로 이동하여 입력창이 최하단 유지되도록 함

with col2:
    st.subheader("설정")

    # VITO 자격증명 버튼
    if st.button("VITO 자격증명 불러오기/저장"):
        try:
            cid, csec = load_or_prompt_vito_credentials()
            st.success("자격증명 확인 완료")
        except Exception as e:
            st.error(f"자격증명 오류: {e}")

    # TTS 설정
    st.session_state.use_tts = st.toggle(
        "TTS 사용",
        value=st.session_state.use_tts,
        help="응답을 음성으로도 재생합니다",
    )
    if st.session_state.use_tts and st.session_state.tts_service is None:
        try:
            project_dir = os.path.dirname(os.path.abspath(__file__))
            svc = TTSService(dir_path=project_dir)
            svc.start()
            st.session_state.tts_service = svc
            st.success("TTS 준비 완료")
        except Exception as e:
            st.session_state.use_tts = False
            st.warning(f"TTS 초기화 실패: {e}")
    if not st.session_state.use_tts and st.session_state.tts_service is not None:
        try:
            st.session_state.tts_service.shutdown()
        except Exception:
            pass
        st.session_state.tts_service = None

    st.divider()

    

    # STT 설정 및 녹음 버튼
    st.session_state.use_stt = st.toggle(
        "STT 사용",
        value=st.session_state.use_stt,
        help="클릭해서 말하면 전사 후 바로 전송합니다",
    )

    if st.session_state.use_stt:
        if st.button("🎙️ 말하기 (무음 2초로 종료)"):
            try:
                # STT 클라이언트 준비
                if st.session_state.stt_client is None:
                    cid, csec = load_or_prompt_vito_credentials()
                    st.session_state.stt_client = VitoSTTClient(client_id=cid, client_secret=csec)
                # 토큰 최신화
                st.session_state.stt_client.jwt_token = get_or_refresh_vito_token(st.session_state.stt_client)

                # 녹음 → 파일 저장
                wav_path = os.path.join("history", f"record_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}.wav")
                os.makedirs(os.path.dirname(wav_path), exist_ok=True)

                with st.spinner("녹음 중... (무음 2초 시 자동 종료)"):
                    st.session_state.stt_client.record_until_silence(
                        wav_path,
                        silence_seconds=2,
                    )

                # 전사
                with st.spinner("전사 중..."):
                    stt_json = st.session_state.stt_client.transcribe_file_and_wait(wav_path)
                    text = extract_transcript(stt_json)

                if not text.strip():
                    st.warning("전사된 텍스트가 비어있습니다.")
                else:
                    # 대화에 바로 전송 (전용 div가 렌더링)
                    reply = chat_with_gpt(
                        text,
                        st.session_state.messages,
                        tts=st.session_state.tts_service,
                        use_tts=st.session_state.use_tts,
                    )
                    try:
                        if hasattr(st, "rerun"):
                            st.rerun()
                        else:
                            st.experimental_rerun()  # type: ignore[attr-defined]
                    except Exception:
                        pass
            except Exception as e:
                st.error(f"STT 실패: {e}")

