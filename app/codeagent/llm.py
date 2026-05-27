from abc import ABC, abstractmethod
import os
import asyncio
import google.generativeai as genai

class BaseLLM(ABC):
    @abstractmethod
    async def generate(self, prompt: str, max_tokens: int = 2000) -> str:
        pass

class GeminiLLM(BaseLLM):
    def __init__(self, model: str = "gemini-1.5-flash", api_key: str = None):
        self.model_name = model
        genai.configure(api_key=api_key or os.getenv("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel(model)

    async def generate(self, prompt: str, max_tokens: int = 2000, json_format: bool = False) -> str:
        try:
            if json_format:
                full_prompt = prompt + "\nRespond ONLY with a valid JSON object, no markdown, no extra text."
            else:
                full_prompt = prompt

            # Gemini is sync, run in thread to keep async
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.model.generate_content(
                    full_prompt,
                    generation_config=genai.types.GenerationConfig(
                        max_output_tokens=max_tokens,
                        temperature=0.2 if json_format else 0.7,
                    )
                )
            )
            return response.text.strip()

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
