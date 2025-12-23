from abc import ABC, abstractmethod
import os
import aiohttp
import asyncio

class BaseLLM(ABC):
    @abstractmethod
    async def generate(self, prompt: str, max_tokens: int = 2000) -> str:
        pass

class OllamaLLM(BaseLLM):
    def __init__(self, model: str = "qwen2.5-coder:3b", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url
    
    async def generate(self, prompt: str, max_tokens: int = 2000, json_format: bool = False) -> str:
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": 0.2 if json_format else 0.7, # Lower temperature for structured output
                }
            }
            if json_format:
                payload["format"] = "json"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=90)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        print(f"Ollama error status {response.status}: {error_text}")
                        return self._fallback_generation(prompt) if not json_format else "{}"
                        
                    result = await response.json()
                    return result.get("response", "")
        except Exception as e:
            print(f"Ollama generation error: {str(e)}")
            return self._fallback_generation(prompt) if not json_format else "{}"
    
    def _fallback_generation(self, prompt: str) -> str:
        """Simple fallback if LLM fails"""
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
