# Process Log — CSCI 599 Assignment 1

## 1. AI tools used

- Clause Opus 5.5 was used to help generate, test, debug. and deploy onto google cloud services.

## 2. Development narrative

I uploaded the file to Claude and asked about the scope of the assignment, what we are supposed to be doing, and what the main outcome or learning objective was. Once it was done explaining to me what the purpose and the objective of the assignment was it then offered to try and attempt and generate the files needed. Once it was done generating I then inserted it into my repo and inspected the files for accuracy and any missing compartments that Claude might have forgotten. When attempting to connect to online services I tried to connect with codex and Claude API and had Claude explain that the subscription I am already paying for does not include API access so it researched and gave me the alternative of using NVIDIA NIM for free. I also had it help install python3.13 as 3.15 "zstandard" wheel build failed.

I chose LangGraph as it was the recommended tech stack and the MCP systems were Tavily and Filesystem were required while Fetch was used because it can read the page, which is useful for context.

For the local run it initially failed because the some of the MCP servers because windows npm install .cmd wrappers as opposed to Linux. When deployed live it was successful, but there was an issue with Fetch failing with "EACCES" at which the agent then switched to Tavily.

WHat I changed that Claude generated was that I made sure to keep `deploy.sh` for the ease of access for the graders. I changed features that Claude generated for codex/OpenAI to NVIDIA NIM and the Nemotron model.

## 3. Verification narrative

The initial run gave a passing 22 and 2 failed due to "RunTimeError" as the even loop is closed in the live tests. After that fix there was only one failing test. There after the last fix gave the passing score of 25/25 on my windows machine

The multi-step tools/call lines that I saw were Local create/read went LLM then `write_file` then LLM then `read_text_file` then LLM. Local search went `tavily_search` then `tavily_extract`. It was the right tool, but when searching for the "latest" query it was stale as the date output was 2024 2025, This was then fixed to show most recent up to date. When searching for for "What is a binary tree?" it made one LLM call with no tools/call lines. With the ssame session_ID it was able to remember earlier requests and when going into a new session_id it didn' remember or recalls the other session_id memory, of which both were answered with no tool calls.

The "/health" of the showed that all three MCP servers, filesystem was rooted at "/app/workspace" and the log showing the agent being ready.

The following queries were tested:

```json
{"query": "My favorite data structure is the heap.", "session_id": "mem1"}
{"query": "What is my favorite data structure?", "session_id": "mem1"}
{"query": "What is my favorite data structure?", "session_id": "mem2"}
```

**Link 1:** https://csci599-a1-308335294462.us-west1.run.app
Link required for submission

**Link 2:** https://csci599-a1-308335294462.us-west1.run.app/docs#/default/chat_chat_post
Visual of the

## 4. What I learned

Some things that the AI couldn't do for me is accepting the Cloud Term of Service, link billing, and choosing the subscription option. I was genuinely impressed with how Claude was able to run and verify things on its own end and generate the amount of files it did, albeit the errors, it was impressive nonetheless. I was also astonished by what and how it did things, it is like a phrase my old Intro to Computer Science teacher said "The computer is only as smart as the user", meaning that the usefulness and what you get out of it is really determined by what you put in it.
