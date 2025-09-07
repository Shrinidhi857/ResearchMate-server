# research_helper.py

import google.generativeai as genai
from dotenv import load_dotenv
import os
import ast
import re

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Initialize model
model = genai.GenerativeModel("gemini-2.0-flash")

def getUserInput(userPrompt):  # step:1
    questions = getNecessaryQuestions(userPrompt=userPrompt)
    return {
        "prompt": userPrompt,
        "questions": questions
    }

def getNecessaryQuestions(userPrompt):
    response = model.generate_content(
        f"You are a Research helper. Your task is to ask the user a few questions "
        f"to get full idea about the topic. Here is the prompt: {userPrompt}. "
        f"Return ONLY a Python list of strings like this: ['question1', 'question2', ...]"
    )

    raw_output = response.text.strip()
    print("Raw Gemini response:", raw_output)

    # Extract list part
    match = re.search(r"\[.*\]", raw_output, re.DOTALL)
    if not match:
        print("Could not find a list in the response.")
        return []

    list_str = match.group(0)

    try:
        questions = ast.literal_eval(list_str)
    except Exception as e:
        print("Error parsing list:", e)
        return []

    return questions
