import os
import sys
from datetime import datetime
import streamlit as st
from util.stt import VitoSTTClient
from util.tts import TTSService
from util.house import House, get_house_instance
from util.launcher import should_launch_streamlit, launch_streamlit
from main import (
    system_message,
    chat_with_gpt,
    save_history,
    extract_transcript,
    get_or_refresh_vito_token,
    load_or_prompt_vito_credentials,
)


if should_launch_streamlit(sys.argv):
    launch_streamlit(os.path.abspath(__file__), sys.argv)
    raise SystemExit(0)

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
if "house" not in st.session_state:
    st.session_state.house = get_house_instance()
else:
    st.session_state.house = get_house_instance()

col1, col2 = st.columns([3, 2], gap="large")

with col1:
    chat_container = st.container(height=560)
    with chat_container:
        for msg in st.session_state.messages[1:]:
            role = msg.get("role")
            content = msg.get("content")
            if not content or role not in ("user", "assistant"):
                continue
            with st.chat_message("user" if role == "user" else "assistant"):
                st.markdown(str(content))

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
        timestamp_str = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        st.session_state.messages.append({"role": "system", "content": f"현재 시각:{timestamp_str}"})
        st.session_state.messages.append({"role": "user", "content": user_text})

        try:
            chat_with_gpt(
                user_text,
                st.session_state.messages,
                tts=st.session_state.tts_service,
                use_tts=st.session_state.use_tts,
                append_user=False,
            )
            st.session_state.house = get_house_instance()
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
                timestamp_str = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
                st.session_state.messages.append({"role": "system", "content": f"현재 시각:{timestamp_str}"})
                st.session_state.messages.append({"role": "user", "content": text_to_send})
                try:
                    chat_with_gpt(
                        text_to_send,
                        st.session_state.messages,
                        tts=st.session_state.tts_service,
                        use_tts=st.session_state.use_tts,
                        append_user=False,
                    )
                    st.session_state.house = get_house_instance()
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
    st.subheader("🏠 방 상태")
    house = st.session_state.house
    status = house.to_dict()

    st.write(f"에어컨: {'켜짐' if status['aircon'] else '꺼짐'}")
    st.write(f"난방: {'켜짐' if status['heater'] else '꺼짐'}")
    st.write(f"TV: {'켜짐' if status['tv'] else '꺼짐'}")
    st.write(f"온도: {status['temperature']}℃")
    st.write(f"채널: {status['channel']}")
    st.write(f"볼륨: {status['volume']}")
    st.write(f"방 상태: {'깨끗함' if status['clean'] else '더러움'}")

    st.divider()

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("에어컨 켜기"):
            house.turn_on_aircon()
            st.rerun()
        if st.button("에어컨 끄기"):
            house.turn_off_aircon()
            st.rerun()
        if st.button("난방 켜기"):
            house.turn_on_heater()
            st.rerun()
        if st.button("난방 끄기"):
            house.turn_off_heater()
            st.rerun()
    with col_b:
        if st.button("TV 켜기"):
            house.turn_on_tv()
            st.rerun()
        if st.button("TV 끄기"):
            house.turn_off_tv()
            st.rerun()
        if st.button("방 청소"):
            house.clean_room()
            st.rerun()
        if st.button("방 더럽히기"):
            house.make_dirty()
            st.rerun()

    st.divider()
    temp_value = st.number_input("온도 설정", min_value=16, max_value=30, value=status["temperature"])
    if st.button("온도 적용"):
        house.set_temperature(int(temp_value))
        st.rerun()

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
                if st.session_state.stt_client is None:
                    cid, csec = load_or_prompt_vito_credentials()
                    st.session_state.stt_client = VitoSTTClient(client_id=cid, client_secret=csec)
                st.session_state.stt_client.jwt_token = get_or_refresh_vito_token(st.session_state.stt_client)

                wav_path = os.path.join("history", f"record_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}.wav")
                os.makedirs(os.path.dirname(wav_path), exist_ok=True)

                with st.spinner("녹음 중... (무음 2초 시 자동 종료)"):
                    st.session_state.stt_client.record_until_silence(
                        wav_path,
                        silence_seconds=2,
                    )

                with st.spinner("전사 중..."):
                    stt_json = st.session_state.stt_client.transcribe_file_and_wait(wav_path)
                    text = extract_transcript(stt_json)

                if not text.strip():
                    st.warning("전사된 텍스트가 비어있습니다.")
                else:
                    chat_with_gpt(
                        text,
                        st.session_state.messages,
                        tts=st.session_state.tts_service,
                        use_tts=st.session_state.use_tts,
                    )
                    st.session_state.house = get_house_instance()
                    try:
                        if hasattr(st, "rerun"):
                            st.rerun()
                        else:
                            st.experimental_rerun()  # type: ignore[attr-defined]
                    except Exception:
                        pass
            except Exception as e:
                st.error(f"STT 실패: {e}")

