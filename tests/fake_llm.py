"""서비스 테스트용 가짜 LLMClient. 호출 인자를 `calls`에 기록하고, 준비한 응답을 차례로 돌려주거나 예외를 던진다."""


class FakeLLM:
    model = "fake-model"

    def __init__(self, responses=()):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def generate_json(self, **kwargs):
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
