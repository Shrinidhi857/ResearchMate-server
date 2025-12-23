from typing import List, Dict, Optional, Any, Union
import re
import json
import asyncio
from pydantic import BaseModel, Field
from .llm import BaseLLM

class ToolCall(BaseModel):
    tool: str = Field(..., description="Name of the tool to call: 'search_docs', 'read_doc', 'read_current_paper', or 'none'")
    args: Dict[str, Any] = Field(default_factory=dict, description="Arguments for the tool")

class AgentThought(BaseModel):
    thought: str = Field(..., description="The internal reasoning of the agent")
    tool_call: Optional[ToolCall] = None
    final_latex: Optional[str] = None

class LaTeXAgent:
    """Agentic LaTeX Assistant that uses tools and reasons before acting"""
    
    def __init__(self, llm: BaseLLM):
        self.llm = llm
        self.max_steps = 5

    def get_system_prompt(self, project_name: str, doc_list: List[Dict]) -> str:
        docs_formatted = "\n".join([f"- ID: {d['id']}, Title: {d['title']}" for d in doc_list])
        
        return f"""You are the 'Antigravity' LaTeX Agent, an expert in research paper writing.
Current Project: {project_name}

AVAILABLE TOOLS:
1. search_docs(query: str): Search project documents titles and keywords. Returns a list of document IDs.
2. read_doc(doc_id: str): Read the full content of a specific document by its ID.
3. read_current_paper(): Read the current LaTeX code of the project paper.
4. none(): Call this when you have enough information to provide the final LaTeX code or response.

REASONING PROCESS:
You must respond in structured JSON format following this schema:
{{
  "thought": "your reasoning about what to do next",
  "tool_call": {{ "tool": "tool_name", "args": {{ ... }} }},
  "final_latex": "The complete, fixed LaTeX code (only when tool is 'none')"
}}

GUIDELINES:
- Start with zero context. If the user asks for something related to project docs, use 'search_docs' or 'read_doc' first.
- Always check the current paper state with 'read_current_paper' before editing.
- Focus on making specific, targeted changes.
- Return ONLY the JSON object.

PROJECT DOCUMENTS AVAILABLE:
{docs_formatted or "No documents uploaded yet."}
"""

    async def run(self, user_request: str, project_id: str, context_fetcher: Any) -> Dict[str, Any]:
        """The main Agentic ReAct loop"""
        
        # 1. Fetch project info for the prompt
        project_info = await context_fetcher.get_project_info(project_id)
        project_name = project_info.get("name", "Untitled")
        doc_list = project_info.get("documents", [])
        
        steps = []
        conversation_history = [
            {"role": "user", "content": user_request}
        ]
        
        current_step = 0
        while current_step < self.max_steps:
            current_step += 1
            
            # Construct prompt
            system_prompt = self.get_system_prompt(project_name, doc_list)
            full_prompt = f"{system_prompt}\n\n"
            
            # Add step history
            for step in steps:
                full_prompt += f"Thought: {step['thought']}\nObservation: {step['observation']}\n"
            
            full_prompt += f"\nUser: {user_request}\nNext Step (JSON):"
            
            # 2. Get LLM Thought
            response_str = await self.llm.generate(full_prompt, json_format=True)
            try:
                thought_data = AgentThought.parse_raw(response_str)
            except Exception as e:
                print(f"DEBUG: Failed to parse agent thought: {e}\nResponse: {response_str}")
                # Fallback: try to extract JSON with regex if it failed
                match = re.search(r'(\{.*\})', response_str, re.DOTALL)
                if match:
                    try:
                        thought_data = AgentThought.parse_raw(match.group(1))
                    except:
                        return {"error": "Failed to parse agent reasoning", "raw": response_str}
                else:
                    return {"error": "Invalid agent response format", "raw": response_str}

            # 3. Handle Tool Call
            if not thought_data.tool_call or thought_data.tool_call.tool == 'none':
                # Final response reached
                return {
                    "thought": thought_data.thought,
                    "latex": thought_data.final_latex,
                    "steps": steps
                }
            
            tool_name = thought_data.tool_call.tool
            args = thought_data.tool_call.args
            
            print(f"DEBUG: Agent calling tool: {tool_name} with args {args}")
            
            # 4. Execute Tool
            observation = "Tool not found"
            if tool_name == "search_docs":
                observation = await context_fetcher.search_docs(project_id, args.get("query", ""))
            elif tool_name == "read_doc":
                observation = await context_fetcher.read_doc(args.get("doc_id", ""))
            elif tool_name == "read_current_paper":
                observation = await context_fetcher.read_current_paper(project_id)
            
            steps.append({
                "thought": thought_data.thought,
                "tool": tool_name,
                "args": args,
                "observation": str(observation)[:2000] # Truncate very long observations
            })
            
            # Signal the thinking process to the manager if possible
            if hasattr(context_fetcher, "signal_thinking"):
                await context_fetcher.signal_thinking(f"Thinking: {thought_data.thought} -> {tool_name}")

        return {"error": "Max reasoning steps reached", "steps": steps}

    async def fix_latex(self, original_code: str, error_log: str) -> str:
        """Fallback for the existing fixed loop if needed, but ideally absorbed into the agentic loop"""
        # For now, keep a simplified version for quick hotfixes
        prompt = f"""You are a LaTeX expert. Fix this error:
ERROR: {error_log[:500]}
CODE:
{original_code[:2000]}

Return ONLY the fixed LaTeX code in a block."""
        response = await self.llm.generate(prompt)
        return self._extract_latex_code(response)

    def _extract_latex_code(self, text: str) -> str:
        """Extract LaTeX code from LLM response"""
        if not text: return ""
        match = re.search(r'```(?:latex)?\s*(.*?)```', text, re.DOTALL | re.IGNORECASE)
        if match: return match.group(1).strip()
        if "\\documentclass" in text:
            start = text.find("\\documentclass")
            end = text.find("\\end{document}")
            if start != -1 and end != -1:
                return text[start:end+14].strip()
        return text.strip()
