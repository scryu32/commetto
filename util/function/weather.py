def get_weather(location: str) -> str:
    """
    특정 지역의 날씨 정보를 반환하는 테스트용 함수
    
    Args:
        location (str): 날씨를 조회할 지역명
        
    Returns:
        str: JSON 형태의 날씨 정보 문자열
    """
    import json
    
    # 매개변수 확인
    if not location:
        return json.dumps({
            "error": "지역명이 제공되지 않았습니다.",
            "location": location
        }, ensure_ascii=False)
    
    # 테스트용 날씨 데이터
    weather_data = {
        "location": location,
        "temperature": "22°C",
        "condition": "맑음",
        "humidity": "65%",
        "wind_speed": "5km/h",
        "description": f"{location}의 현재 날씨는 맑고 기온은 22도입니다.",
        "timestamp": "2025-09-19 14:30:00"
    }
    
    # JSON 문자열로 반환
    return json.dumps(weather_data, ensure_ascii=False)
