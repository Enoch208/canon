import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import anthropic
from dotenv import load_dotenv

DEFAULT_MODEL = "claude-opus-5"
DEFAULT_LOCAL_ENDPOINT = "http://127.0.0.1:1234/v1/chat/completions"
ANTHROPIC_MODEL_PREFIX = "claude-"
NO_THINK_MODELS = ("qwen3",)
EFFORT_UNSUPPORTED = ("haiku-4-5", "sonnet-4-5", "-3-5-", "-3-")
DEFAULT_EFFORT = "medium"
NO_THINK_SUFFIX = " /no_think"
UNKNOWN_TOKEN = "UNKNOWN"
SYSTEM_PROMPT = (
    "You answer questions about an enterprise using only the provided context documents. "
    "Give a direct answer with the specific values asked for. If the context does not "
    f"contain enough information to answer, reply with exactly {UNKNOWN_TOKEN} and nothing else."
)


@dataclass(frozen=True, slots=True)
class Answer:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    stop_reason: str


class AnswerModel(Protocol):
    @property
    def name(self) -> str: ...

    def answer(self, question: str, context: str) -> Answer: ...


def prompt_for(question: str, context: str) -> str:
    return f"Context documents:\n\n{context}\n\nQuestion: {question}\n\nAnswer:"


def supports_effort(model: str) -> bool:
    return not any(marker in model for marker in EFFORT_UNSUPPORTED)


class AnthropicAnswerModel:
    def __init__(self, model: str = DEFAULT_MODEL, max_tokens: int = 2048) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._client = anthropic.Anthropic()
        self._effort = DEFAULT_EFFORT if supports_effort(model) else None

    @property
    def name(self) -> str:
        return self._model

    def answer(self, question: str, context: str) -> Answer:
        options: dict[str, object] = {}
        if self._effort is not None:
            options["output_config"] = {"effort": self._effort}
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt_for(question, context)}],
            **options,
        )
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        return Answer(
            text=text,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=str(response.stop_reason),
        )


class LocalAnswerError(RuntimeError):
    pass


class LocalAnswerModel:
    def __init__(
        self,
        model: str,
        endpoint: str = DEFAULT_LOCAL_ENDPOINT,
        max_tokens: int = 512,
        timeout_seconds: float = 1800.0,
    ) -> None:
        self._model = model
        self._endpoint = endpoint
        self._max_tokens = max_tokens
        self._timeout_seconds = timeout_seconds
        self._suffix = NO_THINK_SUFFIX if any(m in model for m in NO_THINK_MODELS) else ""

    @property
    def name(self) -> str:
        return f"{self._model} @ {self._endpoint}"

    def answer(self, question: str, context: str) -> Answer:
        payload = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt_for(question, context) + self._suffix},
            ],
        }
        request = urllib.request.Request(
            self._endpoint,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                body = json.loads(response.read().decode())
        except urllib.error.HTTPError as error:
            raise LocalAnswerError(f"{self._endpoint}: {error.read().decode()[:300]}") from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise LocalAnswerError(f"{self._endpoint} unreachable: {error}") from error
        choice = body["choices"][0]
        usage = body.get("usage") or {}
        return Answer(
            text=(choice["message"].get("content") or "").strip(),
            model=body.get("model", self._model),
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            stop_reason=str(choice.get("finish_reason", "")),
        )


class GuardedAnswerModel:
    def __init__(self, model: AnswerModel) -> None:
        self._model: AnswerModel | None = model
        self._name = model.name
        self.answered = 0
        self.failure: str | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def available(self) -> bool:
        return self._model is not None

    def answer(self, question: str, context: str) -> Answer | None:
        if self._model is None:
            return None
        try:
            answer = self._model.answer(question, context)
        except (anthropic.APIError, LocalAnswerError) as error:
            self.failure = f"{type(error).__name__}: {error}"
            self._model = None
            return None
        self.answered += 1
        return answer


def load_env_file(root: Path) -> bool:
    env_file = root / ".env"
    if not env_file.exists():
        return False
    load_dotenv(env_file, override=False)
    return True


def credentials_present() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def local_endpoint() -> str:
    return os.environ.get("CANON_LOCAL_ENDPOINT", DEFAULT_LOCAL_ENDPOINT)


def load_answer_model(model: str = DEFAULT_MODEL) -> tuple[GuardedAnswerModel | None, str]:
    if not model.startswith(ANTHROPIC_MODEL_PREFIX):
        return GuardedAnswerModel(LocalAnswerModel(model, local_endpoint())), ""
    if not credentials_present():
        return None, "ANTHROPIC_API_KEY not set; answer model not run"
    try:
        return GuardedAnswerModel(AnthropicAnswerModel(model)), ""
    except anthropic.AnthropicError as error:
        return None, f"anthropic client unavailable: {error}"
