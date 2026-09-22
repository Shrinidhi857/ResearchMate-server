from abc import ABC, abstractmethod
import os
import asyncio
from google import genai
from google.genai import types

class BaseLLM(ABC):
    @abstractmethod
    async def generate(self, prompt: str, max_tokens: int = 2000, json_format: bool = False) -> str:
        pass

class GeminiLLM(BaseLLM):
    def __init__(self, model: str = "gemini-2.5-flash", api_key: str = None):
        self.model = model
        self.client = genai.Client(
            api_key=api_key or os.getenv("GEMINI_API_KEY")
        )

    async def generate(self, prompt: str, max_tokens: int = 2000, json_format: bool = False) -> str:
        try:
            if json_format:
                full_prompt = prompt + "\nRespond ONLY with a valid JSON object, no markdown, no extra text."
            else:
                full_prompt = prompt

            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=max_tokens,
                    temperature=0.2 if json_format else 0.7,
                    response_mime_type="application/json" if json_format else None,
                ),
            )
            return response.text.strip() if response.text else ""

        except Exception as e:
            print(f"Gemini generation error: {str(e)}")
            return "{}" if json_format else self._fallback_generation()

    def _fallback_generation(self) -> str:
        return r"""\documentclass{article}
\usepackage{amsmath}
\usepackage{graphicx}
\title{Generated Document}
\author{LaTeX Agent}
\date{\today}
\begin{document}
\maketitle
\section{Introduction}
This is a fallback document generated when the LLM is unavailable.
\end{document}"""

