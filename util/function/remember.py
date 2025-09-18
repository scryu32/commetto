import os
import json
from datetime import datetime
from typing import Optional


def remember(description: Optional[str]) -> str:
    """
    사용자가 요청한 내용을 영구 저장소에 기록합니다.

    입력:
        description: 저장할 내용 (문자열)

    출력:
        JSON 문자열 (status, message, saved 객체 포함)
    """
    try:
        if not isinstance(description, str) or not description.strip():
            return json.dumps(
                {
                    "status": "error",
                    "message": "유효한 description이 필요합니다.",
                    "saved": None,
                },
                ensure_ascii=False,
            )

        description = description.strip()

        # 저장 경로: history/memories.jsonl (라인 단위 JSON)
        os.makedirs("history", exist_ok=True)
        path = os.path.join("history", "memories.jsonl")

        now = datetime.now().replace(microsecond=0).isoformat()
        record = {
            "id": f"mem_{int(datetime.now().timestamp())}",
            "description": description,
            "created_at": now,
        }

        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False))
            f.write("\n")

        return json.dumps(
            {
                "status": "ok",
                "message": "저장 완료",
                "saved": {"description": description, "created_at": now, "path": path},
            },
            ensure_ascii=False,
        )
    except Exception as e:
        return json.dumps(
            {
                "status": "error",
                "message": f"저장 중 오류: {e}",
                "saved": None,
            },
            ensure_ascii=False,
        )


__all__ = ["remember"]


