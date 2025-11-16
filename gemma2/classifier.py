import requests
import json
import re

def summarize_research_paper(text: str):
    """
    Send research paper text to Ollama (gemma2) and get structured JSON summary.
    """
    url = "http://localhost:11434/api/generate"

    prompt = f"""You are an academic summarizer. Analyze the following research paper and respond ONLY with valid JSON. Do not include any explanations, markdown formatting, or extra text.

Your response must be ONLY this JSON structure:
{{"Title": "paper title here", "Methodology": "methodology description", "Results": "key results", "Conclusion": "main conclusion"}}

Research paper text:
{text}

Remember: Output ONLY the JSON object, nothing else."""

    data = {
        "model": "gemma2:2b",
        "prompt": prompt,
        "stream": False,  # Disable streaming for cleaner output
        "format": "json"  # Request JSON format (if supported by your Ollama version)
    }

    try:
        response = requests.post(url, json=data)
        response.raise_for_status()
        
        result = response.json()
        output = result.get("response", "")
        
        # Method 1: Try direct JSON parsing
        try:
            result_json = json.loads(output)
            return {"success": True, "data": result_json}
        except json.JSONDecodeError:
            pass
        
        # Method 2: Extract JSON using regex (handles markdown code blocks)
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', output, re.DOTALL)
        if json_match:
            try:
                result_json = json.loads(json_match.group(0))
                return {"success": True, "data": result_json}
            except json.JSONDecodeError:
                pass
        
        # Method 3: Clean common markdown artifacts
        cleaned = output.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned.replace("```json", "", 1)
        if cleaned.startswith("```"):
            cleaned = cleaned.replace("```", "", 1)
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        
        try:
            result_json = json.loads(cleaned.strip())
            return {"success": True, "data": result_json}
        except json.JSONDecodeError:
            return {"success": False, "raw_output": output, "error": "Could not parse JSON"}

    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


# Alternative version with streaming (if you prefer it)
def summarize_research_paper_streaming(text: str):
    """
    Streaming version with JSON extraction.
    """
    url = "http://localhost:11434/api/generate"

    prompt = f"""Respond ONLY with valid JSON in this exact format:
{{"Title": "...", "Methodology": "...", "Results": "...", "Conclusion": "..."}}

Research paper:
{text}

JSON only, no other text:"""

    data = {
        "model": "gemma2:2b",
        "prompt": prompt,
        "stream": True
    }

    try:
        response = requests.post(url, json=data, stream=True)
        response.raise_for_status()
        
        output = ""
        for line in response.iter_lines():
            if line:
                message = json.loads(line)
                if not message.get("done", False):
                    output += message.get("response", "")

        # Extract and parse JSON (using same methods as above)
        output = output.strip()
        
        # Try direct parsing first
        try:
            result_json = json.loads(output)
            return {"success": True, "data": result_json}
        except json.JSONDecodeError:
            pass
        
        # Extract JSON from potential markdown/text wrapper
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', output, re.DOTALL)
        if json_match:
            try:
                result_json = json.loads(json_match.group(0))
                return {"success": True, "data": result_json}
            except json.JSONDecodeError:
                pass
        
        return {"success": False, "raw_output": output, "error": "Could not extract valid JSON"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# Usage example
"""
if __name__ == "__main__":
    
    
    result = summarize_research_paper(sample_text)
    
    if result["success"]:
        print("✓ Successfully parsed JSON:")
        print(json.dumps(result["data"], indent=2))
    else:
        print("✗ Failed to get JSON:")
        print(f"Error: {result.get('error', 'Unknown')}")
        print(f"Raw output: {result.get('raw_output', 'N/A')}")
"""