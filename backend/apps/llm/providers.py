from __future__ import annotations

from abc import ABC, abstractmethod

from groq import Groq


class BaseLLMProvider(ABC):
    @abstractmethod
    def generate_json(self, prompt: str) -> str:
        raise NotImplementedError


class GroqLLMProvider(BaseLLMProvider):
    def __init__(self, api_key: str, model: str, temperature: float = 0.0) -> None:
        self.client = Groq(api_key=api_key)
        self.model = model
        self.temperature = temperature

    def generate_json(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a strict JSON-only intent parser."},
                {"role": "user", "content": prompt},
            ],
        )
        content = response.choices[0].message.content or "{}"
        return content
