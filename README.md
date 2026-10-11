# A2A: a code review agent and a client

Companion code for the blog post *Building Open, Decentralized AI Agents With Google A2A*.

- `server/` — the A2A agent (`main.py`), its `Dockerfile` and requirements
- `client/` — the A2A client (`client.py`) and its requirements

## Prerequisites

- Docker
- Python 3.10+
- An OpenAI API key

## Run

```bash
cp .env.example .env            # add your OPENAI_API_KEY

# Terminal 1: server
docker build -t a2a-code-review-agent server/
docker run --rm -p 9999:9999 --env-file .env a2a-code-review-agent

# Terminal 2: client
pip install -r client/requirements.txt
python client/client.py my.diff                         # review a diff file
git diff | python client/client.py                      # review uncommitted changes in a repo
python client/client.py README.md                       # not a diff: the agent asks for one
```

The agent card is served at <http://localhost:9999/.well-known/agent-card.json>.

## Notes

- If you publish the container on another host or port, set `PUBLIC_URL` so the Agent Card advertises a reachable address: `-p 8080:9999 -e PUBLIC_URL=http://localhost:8080/`, and update `AGENT_URL` in `client/client.py` to match.
- The whole diff is sent to the model with no size limit; add one before exposing this agent.
- SDKs are pinned (`a2a-sdk==1.2.2`, `openai==3.28.0`); the A2A 1.x API differs from 0.2/0.3.
