# Process Log — CSCI 599 Assignment 1

<!--
HOW TO USE THIS FILE (delete this comment before submitting)

This is a skeleton, not a finished log. The assignment grades AI-sounding logs
skeptically and requires your own voice, so every section must be written by you.
Under each heading there are FACTS from the AI-assisted session and QUESTIONS
to answer. Use them as raw material, rewrite in your own words, and delete the
notes. Add what happened after this session: running it, deploying, what broke,
and what you changed.
-->

## 1. AI tools used

- Claude (Opus 5.5, claude.ai) — generated the README, the agent code, the tests, and the deploy files
- `<add anything else you used: ChatGPT, Copilot, Cursor, Gemini, Ollama models, ... with versions>`

## 2. Development narrative (200–300 words, your voice)

<!--
Facts to draw from (rewrite, don't paste):
- Started by giving Claude the assignment PDF and asking for a README covering the scope, steps, and how to run.
  Prompt: "could you make a readme file for the scope of this assignment which includes steps and how to run?"
- Then asked it to build the files.
  Prompt: "please please build the files."
- Picked LangGraph + FastAPI + langchain-mcp-adapters (the course's recommended stack); filesystem + Tavily + fetch as the three MCP servers.
- Issues found during the build:
  * The sample Dockerfile in the handout installs packages to /root/.local and then switches to a non-root
    user, who can't read /root. Fixed by installing to /usr/local.
  * The sample deploy command only passes OPENAI_API_KEY, so Tavily would have no key on Cloud Run.
  * If the agent hit the step limit right after the LLM asked for a tool, the saved history ended with
    an unanswered tool call, which would break the next turn in that session. Added a repair step (_close_interrupted_turn).
  * The test fake LLM reused one message object, so LangGraph's message reducer overwrote history
    instead of appending. Fixed by copying the message each time.
  * MCP stdio servers only get a minimal environment, so the Tavily key has to be passed explicitly in mcp_config.json.

Questions to answer in your own words:
- Why did you pick LangGraph and these MCP servers?
- What happened when you first ran it locally? When you deployed?
- Where did you get stuck, and what got you unstuck? (Include any prompts you used to debug.)
- Did you change anything Claude generated? Why?
-->

## 3. Verification narrative

<!--
Facts:
- 21 offline pytest tests (pytest -v) use the REAL filesystem and fetch MCP servers and a scripted fake LLM.
  They cover tools/list, tools/call round trips, tool execution errors, an unreachable server, a server
  that prints garbage, a malformed tool result, an unsupported content type, a server crashing mid-call,
  tool chaining, no-tool answers, session memory and isolation, the loop guard, and the HTTP error codes.
- tests/fake_servers/broken_server.py is a deliberately broken MCP server, so the failure modes are tested
  over a real stdio transport, not mocked.
- The 3 live tests in tests/test_live.py need your OpenAI key. They were NOT run during the Claude session
  (no API access there), so run them yourself and record the results.
- The Docker image was NOT built during the Claude session (Docker Hub was blocked there), so record your
  own docker build/run results.

Do these yourself and write what you saw:
- pytest -v and pytest tests/test_live.py -v (results, any failures)
- Watch the "tools/call ->" log lines while asking a multi-step question. Did the agent pick the right tools?
- Break a server on purpose (bad command in mcp_config.json): what did /health and the agent do?
- Ask a no-tool question: did it avoid tools?
- Memory: two turns with the same session_id, then a new session_id
- Deployed URL: the same checks against Cloud Run
-->

## 4. What I learned (2–3 sentences)

<!--
What couldn't the AI do that you had to figure out yourself? For example: GCP project and billing setup,
debugging the live deployment, judging whether tool selection was actually right, understanding why
the loop-back edge matters, etc. Must be genuinely yours.
-->
