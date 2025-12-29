from typing import List, Dict, Optional, Any, Union
import re
import json
import asyncio
from pydantic import BaseModel, Field
from .llm import BaseLLM
from .utils import AgentConfig

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
        self.max_steps = AgentConfig.MAX_STEPS

    def get_system_prompt(self, project_name: str, doc_list: List[Dict], document_ids: Optional[List[str]] = None, current_step: int = 0, max_steps: int = 20) -> str:
        # Filter documents if specific IDs are provided
        if document_ids:
            filtered_docs = [d for d in doc_list if d['id'] in document_ids]
            docs_formatted = "\n".join([f"- ID: {d['id']}, Title: {d['title']}" for d in filtered_docs])
            doc_context = f"USER PRE-SELECTED DOCUMENTS (focus on these):\n{docs_formatted or 'None of the selected IDs were found.'}"
        else:
            docs_formatted = "\n".join([f"- ID: {d['id']}, Title: {d['title']}" for d in doc_list])
            doc_context = f"PROJECT DOCUMENTS AVAILABLE:\n{docs_formatted or 'No documents uploaded yet.'}"
        
        # Add urgency warning if approaching max steps
        urgency_warning = ""
        if current_step >= max_steps * 0.7:  # 70% of max steps
            urgency_warning = f"\n⚠️ WARNING: You are at step {current_step}/{max_steps}. You MUST call 'none' tool soon to provide your final answer!\n"
        
        return f"""You are the 
         LaTeX Agent, an expert in research paper writing.
Current Project: {project_name}
{urgency_warning}
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
  "final_latex": "The complete, updated LaTeX code (only when tool is 'none')"
}}

CRITICAL EDITING GUIDELINES:
- **INCREMENTAL EDITING**: Make targeted changes, NOT complete rewrites!
- **PRESERVE EXISTING CONTENT**: Keep all existing sections, formatting, and structure unless explicitly asked to remove them.
- **TARGETED MODIFICATIONS**: Only modify the specific parts mentioned in the user's request.
- **ADD, DON'T REPLACE**: When adding new sections, insert them at appropriate locations while keeping existing content.
- **ANALYZE BEFORE EDITING**: Always use 'read_current_paper' to understand the existing structure before making changes.

EDITING WORKFLOW:
1. Read the current paper with 'read_current_paper'
2. Identify exactly what needs to change based on user request
3. Preserve all existing content that should remain
4. Make only the specific additions/modifications requested
5. Return the COMPLETE paper with targeted changes applied

EXAMPLES:
- User: "Add a methodology section" → Insert new methodology section, keep everything else
- User: "Update the introduction" → Modify only introduction, preserve all other sections
- User: "Add citations to related work" → Add citations to that section only, keep rest unchanged
- User: "Remove the conclusion" → Remove only conclusion section, keep everything else

STEP LIMITS:
- You have a MAXIMUM of {max_steps} reasoning steps. Use them wisely!
- DO NOT repeat the same tool call with the same arguments.
- After gathering information (1-3 tool calls), you MUST call 'none' to provide your answer.
- ALWAYS call 'none' tool to finish. Never leave the user waiting!
- Return ONLY the JSON object.

{doc_context}
"""

    async def run(self, user_request: str, project_id: str, context_fetcher: Any, document_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """The main Agentic ReAct loop"""
        
        # 1. Fetch project info for the prompt
        project_info = await context_fetcher.get_project_info(project_id)
        project_name = project_info.get("name", "Untitled")
        doc_list = project_info.get("documents", [])
        
        # Validate document IDs if provided
        if document_ids:
            valid_ids = {d['id'] for d in doc_list}
            invalid_ids = [did for did in document_ids if did not in valid_ids]
            if invalid_ids:
                return {
                    "error": f"Invalid document IDs: {', '.join(invalid_ids)}",
                    "steps": []
                }
        
        steps = []
        conversation_history = [
            {"role": "user", "content": user_request}
        ]
        
        # Track tool calls to detect loops
        tool_call_history = []
        
        current_step = 0
        while current_step < self.max_steps:
            current_step += 1
            
            # Construct prompt with optional document filtering and current step info
            system_prompt = self.get_system_prompt(project_name, doc_list, document_ids, current_step, self.max_steps)
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
            
            # Smarter loop detection for complex tasks
            tool_signature = f"{tool_name}:{json.dumps(args, sort_keys=True)}"
            
            # Check if this is a consecutive repeat (calling same tool twice in a row with same args)
            is_consecutive_repeat = len(tool_call_history) > 0 and tool_call_history[-1] == tool_signature
            
            # For non-consecutive repeats, be more lenient to allow multi-document tasks
            # Only trigger if we've done 5+ steps AND repeating exact same call
            is_loop_after_gathering = tool_signature in tool_call_history and len(steps) >= 5
            
            # Special case: Allow reading different documents (different doc_ids)
            # Only flag as loop if reading the SAME document twice
            if tool_name == "read_doc" and not is_consecutive_repeat:
                # Check if we're reading a different document
                current_doc_id = args.get("doc_id", "")
                previous_doc_ids = [
                    step.get("args", {}).get("doc_id", "") 
                    for step in steps 
                    if step.get("tool") == "read_doc"
                ]
                # If this is a new document, don't consider it a loop
                if current_doc_id and current_doc_id not in previous_doc_ids:
                    is_loop_after_gathering = False
            
            if is_consecutive_repeat or is_loop_after_gathering:
                print(f"DEBUG: Loop detected! Agent called {tool_signature} again (consecutive={is_consecutive_repeat}, after_gathering={is_loop_after_gathering}, steps={len(steps)})")
                
                # Force the agent to generate a final answer based on what it has learned
                force_completion_prompt = f"""You are stuck in a loop. Based on the information you've gathered so far, provide your final answer NOW.

User Request: {user_request}

Information gathered from {len(steps)} steps:
{chr(10).join([f"- Step {i+1} - {s['tool']}: {s['observation'][:400]}" for i, s in enumerate(steps[-5:])])}

You have enough information. Provide your final LaTeX code with the requested changes. Return ONLY a JSON object:
{{
  "thought": "Completing with available information",
  "tool_call": {{"tool": "none", "args": {{}}}},
  "final_latex": "Your complete LaTeX code here with all requested modifications"
}}
"""
                
                try:
                    forced_response = await self.llm.generate(force_completion_prompt, json_format=True, max_tokens=4000)
                    forced_thought = AgentThought.parse_raw(forced_response)
                    return {
                        "thought": "Loop detected - forced completion with gathered information",
                        "latex": forced_thought.final_latex,
                        "steps": steps,
                        "warning": "Agent was stuck in a loop and forced to complete"
                    }
                except Exception as e:
                    print(f"DEBUG: Failed to force completion: {e}")
                    return {
                        "thought": "Loop detected but failed to generate completion",
                        "latex": None,
                        "steps": steps,
                        "error": "Agent was stuck in a loop and could not generate a final answer"
                    }
            
            tool_call_history.append(tool_signature)
            
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
                "observation": str(observation)[:AgentConfig.MAX_OBSERVATION_LENGTH]
            })
            
            # Signal the thinking process to the manager if possible
            if hasattr(context_fetcher, "signal_thinking"):
                await context_fetcher.signal_thinking(f"Thinking: {thought_data.thought} -> {tool_name}")

        # If we reach max steps, force a completion with a helpful message
        print(f"DEBUG: Max steps ({self.max_steps}) reached. Forcing completion.")
        return {
            "error": "Max reasoning steps reached. The agent needs more steps or simpler instructions.",
            "steps": steps,
            "suggestion": "Try breaking down your request into smaller tasks or increase AGENT_MAX_STEPS."
        }

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
