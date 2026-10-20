#!/usr/bin/env python3
"""Purpose: run the image scripts/build-omega-image.sh built with upstream's mock LLM provider and test
channel, and pass only when GoalChainer answers through Omega's loop as the image is configured, in two
runs: offline, reading text from the committed Jev replay cache with no key; and through Omega's
gateway, where a fake TYPESAFE_API_KEY given to the container reaches a local TypeSafe stand-in over
verified TLS only as the gateway's bearer token, no agent process holds it, and the answer equals the
offline run's; and only when the gateway's /typesafe/ route forwards to a stand-in whose certificate
chains to the CA it trusts and names its host, and refuses, before any request reaches it, one signed by
another CA or naming another host; and only when the image's pymetta is, file for file, the wheel the
verified native wheel directory its lock names publishes. No hosted model or service is called.

    scripts/check-omega-image.py IMAGE LOG

Each run puts the agent in one container of IMAGE and the mock side and the stand-in in two more, on a
private Docker network, so the check binds no host port and runs alike on a Linux engine and under
Docker Desktop. The mock side is this script with --mock-side, run with the image's python3 against the
pinned Omega's own Autotests/mock, whose servers need a Linux select.poll. The stand-in is this script
with --typesafe-side, run in GoalChainer's environment, answering /v1/systemone from the committed
replay cache over TLS as typesafe.check, a name only the run's own network resolves. Each gateway case
starts the image's gateway alone, as the entrypoint starts it, beside a stand-in holding that case's
certificate. A test CA, a second CA nobody trusts and their certificates are made for each check in a
container of the image, in a Docker volume the containers mount read-only. Every run points
TYPESAFE_UPSTREAM_URL at a stand-in, so no request can reach the hosted service, and runs the agent with
HF_HUB_OFFLINE=1, so none reaches Hugging Face. Whether api.typesafe.ai's own certificate chain verifies
is not checked here: that takes the hosted service. The native wheel directories are this checkout's,
as scripts/native-wheels.py place verifies them, from native-wheels/ or GOALCHAINER_NATIVE_WHEELS, and
the image's own copy of that script checks its environment against them. LOG receives every
container's output. The exit status is 0 when every run and case passes and 1 otherwise, with the
reasons on standard error.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# The text the plugin's own process test reads offline, so the committed replay cache answers every
# question the incident domain asks of it.
# am[verifies a-irp-verify-free-text-1018@908c73]
TEXT = "Checkout is down. Raw logs include customer emails. Engineering needs the incident room."
STANDIN_PORT = 8765
REPLAY_CACHE = "/opt/goalchainer/tests/data/jev"
# Where the check's TLS material is mounted, and the name the stand-ins answer to on their network.
TLS_DIR = "/opt/goalchainer-check-tls"
STANDIN_HOST = "typesafe.check"
UPSTREAM = f"https://{STANDIN_HOST}:{STANDIN_PORT}/"

# The check's TLS material, made with the image's openssl: a test CA the gateway trusts, a rogue CA it
# does not, and three stand-in certificates, typesafe.check by each CA and elsewhere.check by the test
# CA. Each lasts two days, long enough for one check.
# am[verifies a-integrate-gateway-tls-verification-1018@ace531]
TLS_MATERIAL = r"""set -euo pipefail
cd "$1"
authority() {
  openssl req -x509 -newkey rsa:2048 -nodes -days 2 -subj "/CN=$2" \
    -addext basicConstraints=critical,CA:TRUE -addext keyUsage=critical,keyCertSign,cRLSign \
    -keyout "$1.key" -out "$1.pem" 2>/dev/null
}
leaf() {
  openssl req -newkey rsa:2048 -nodes -subj "/CN=$3" -keyout "$1.key" -out "$1.csr" 2>/dev/null
  printf 'subjectAltName=DNS:%s\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n' "$3" > "$1.ext"
  openssl x509 -req -in "$1.csr" -CA "$2.pem" -CAkey "$2.key" -CAcreateserial -days 2 -extfile "$1.ext" \
    -out "$1.pem" 2>/dev/null
}
authority ca "GoalChainer check CA"
authority rogue-ca "GoalChainer check rogue CA"
leaf trusted ca typesafe.check
leaf rogue rogue-ca typesafe.check
leaf wronghost ca elsewhere.check
chmod 0644 ./*
"""

# The gateway's cases: the stand-in's certificate, the status the route must answer, and the line
# nginx must log when it refuses. Only the trusted stand-in may see a request.
# am[verifies a-integrate-gateway-tls-verification-1018@ace531] am[rests-on c-irp-nginx-upstream-verify-1018@271329]
CASES = {
    "trusted": ("trusted", 200, None),
    "untrusted": ("rogue", 502, "upstream SSL certificate verify error"),
    "wrong-host": ("wronghost", 502, f'upstream SSL certificate does not match "{STANDIN_HOST}"'),
}


# A review of the packaged incident domain; with text, the reader reads it, else no reader is asked.
# am[verifies a-oc-plugin-stock-start-1018@f9e0a5] am[verifies a-irp-verify-free-text-1018@908c73]
def review(review_id: str, text: str | None) -> dict:
    request = {
        "operation": "review",
        "domain": {"packaged": "incident"},
        "context": {
            "review_id": review_id,
            "subject": "checkout",
            "trigger": "incident-report",
            "as_of": "2026-10-16T09:00:00+00:00",
            "authority": "advisory",
            "policy_version": "incident-v1",
            "readings": [],
        },
        "inference_budget": 1000000000,
        "timeout_seconds": 600,
    }
    if text is not None:
        request["reading"] = {"text": text, "observed_at": "2026-10-16T09:00:00+00:00", "valid_until": None}
    return request


OBSERVATIONS = review("omega-image-check", None)
READING = review("omega-image-check-text", TEXT)

# What the mock LLM asks the agent in each run and the plugin settings the agent starts with, as an
# operator passes them to docker run. The offline run keeps the image's defaults, Jev offline and no
# key, and names the committed cache; the gateway run turns Jev on with an empty answer cache in the
# agent's /tmp and gives the container a key.
# am[verifies a-irp-verify-free-text-1018@908c73] am[rests-on c-irp-contract-1018@3ed0b0]
RUNS = {
    "offline": {"calls": (OBSERVATIONS, READING), "arguments": (f"goalchainerJevCache={REPLAY_CACHE}",),
                "key": False},
    "gateway": {"calls": (READING,), "arguments": ("goalchainerJevOffline=0", "goalchainerJevCache=/tmp/goalchainer-jev"),
                "key": True},
}


# Each wait polls once a second, since neither the mock's queue nor a container's log offers an event
# to wait on; a wait that outlasts its seconds names what never happened.
# am[verifies a-oc-plugin-stock-start-1018@f9e0a5]
def wait_for(predicate: Callable[[], bool], what: str, seconds: int) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(1)
    raise SystemExit(f"no {what} within {seconds}s")


# The mock side, inside the image: the pinned Omega's controller and channel server listen on the
# private network, where the agent's mockprovider and mockchannel reach them by this container's name.
# The agent's provider connects at its first LLM call, so a refused set_answer is asked again until the
# loop is up, and the message goes only after the scripted answer is in place.
# am[verifies a-oc-plugin-stock-start-1018@f9e0a5] am[implements a-oc-check-mock-in-container-1018@7185d3]
def mock_side(tag: str, name: str) -> int:
    omega = Path(os.environ["OMEGA_DIR"])
    sys.path[:0] = [str(omega / "Autotests" / "mock"), str(omega / "src")]
    from comm import COMM_MOCK_PORT, CommMockServer  # noqa: PLC0415 (only the image holds these)
    from llm import LLM_MOCK_PORT, LlmMockController  # noqa: PLC0415

    llm = LlmMockController(("0.0.0.0", LLM_MOCK_PORT))
    comm = CommMockServer(("0.0.0.0", COMM_MOCK_PORT))
    try:
        prompt = f"REQ-{tag} review the checkout incident with GoalChainer"
        done = f"reviewed-{tag}"
        calls = [["goalchainer-request", {"json_request": json.dumps(call)}] for call in RUNS[name]["calls"]]
        calls.append(["send", {"content": done}])
        wait_for(lambda: llm.set_answer(prompt, calls, timeout=5), "agent loop taking the scripted calls", 900)
        wait_for(lambda: comm.send_message(prompt, timeout=5), "test channel taking the message", 180)
        received: list[str] = []

        def answered() -> bool:
            message = comm.getLastMessage()
            if message:
                received.append(message)
            return done in received

        wait_for(answered, "send of the scripted reply on the test channel", 900)
        print(f"mock-side: the channel received {received!r}", flush=True)
        return 0
    finally:
        llm.stop(5)
        comm.stop(5)


# The TypeSafe stand-in: Jev's /v1/systemone answered from the committed replay cache, each question
# keyed as the reader's AnswerCache keys it, so the reader gets exactly the answers it replays offline,
# and /v1/models answered with no models, for the gateway's cases. It answers 404 for a question the
# cache lacks, and prints each request's method, path, Authorization header, encoding and missing
# questions as one line the check reads. It serves TLS with the certificate STANDIN_CERT names.
# Time: one cache file read per question asked.
# am[verifies a-irp-verify-free-text-1018@908c73] am[rests-on 060aea0d@012966]
# am[verifies a-integrate-gateway-tls-verification-1018@ace531]
def typesafe_side() -> int:
    import ssl  # noqa: PLC0415
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: PLC0415

    from goal_chainer.semantic_reader import AnswerCache  # noqa: PLC0415 (GoalChainer's environment)

    cache = AnswerCache(Path(REPLAY_CACHE))

    class Replay(BaseHTTPRequestHandler):
        def _reply(self, status: int, reply: dict, seen: dict) -> None:
            print(f"typesafe-side: {json.dumps({'method': self.command, 'path': self.path, 'authorization': self.headers.get('Authorization'), **seen})}",
                  flush=True)
            data = json.dumps(reply).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802 (http.server's name)
            self._reply(200, {"models": []}, {})

        def do_POST(self) -> None:  # noqa: N802 (http.server's name)
            body = self.rfile.read(int(self.headers["Content-Length"]))
            encoding = self.headers.get("Content-Encoding")
            if encoding == "zstd":
                from compression.zstd import decompress  # noqa: PLC0415 (typesafe-sdk compresses on 3.14)

                body = decompress(body)
            request = json.loads(body)
            answers, missing, model = {}, [], None
            for question, spec in request["questions"].items():
                entry = cache.get(cache.key(request["model"], request["state"], spec))
                if entry is None or "refused" in entry:
                    missing.append(question)
                    continue
                probabilities = entry["probabilities"]
                choice = max(probabilities, key=probabilities.get)
                answers[question] = {"type": "choice", "choice": choice, "confidence": probabilities[choice],
                                     "probabilities": probabilities}
                model = entry["model"]
            reply = ({"detail": {"missing": missing}} if missing
                     else {"model": model, "answers": answers, "usage": {"input_tokens": 1, "output_tokens": 0}})
            self._reply(404 if missing else 200, reply,
                        {"encoding": encoding, "questions": len(request["questions"]), "missing": missing})

    server = ThreadingHTTPServer(("0.0.0.0", STANDIN_PORT), Replay)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(f"{TLS_DIR}/{os.environ['STANDIN_CERT']}.pem", f"{TLS_DIR}/{os.environ['STANDIN_CERT']}.key")
    server.socket = context.wrap_socket(server.socket, server_side=True)
    print("typesafe-ready", flush=True)
    server.serve_forever()
    return 0


# am[verifies a-oc-plugin-stock-start-1018@f9e0a5]
def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check)


# A stand-in on NETWORK under the name typesafe.check, serving CERTIFICATE from the check's material,
# once it is listening, so nothing that asks it can meet a port not yet open.
# am[verifies a-integrate-gateway-tls-verification-1018@ace531]
def start_standin(image: str, network: str, container: str, volume: str, certificate: str) -> None:
    docker("run", "-d", "--name", container, "--network", network, "--network-alias", STANDIN_HOST,
           "-v", f"{volume}:{TLS_DIR}:ro", "-e", f"STANDIN_CERT={certificate}",
           "--entrypoint", "/opt/goalchainer/.venv/bin/python", image,
           "/opt/goalchainer/scripts/check-omega-image.py", "--typesafe-side")
    wait_for(lambda: "typesafe-ready" in docker("logs", container, check=False).stdout, f"{container} listening", 120)


# What a stand-in was asked, one object per request, from the lines it printed.
# am[verifies a-irp-verify-free-text-1018@908c73]
def asked_of(container: str) -> list[dict]:
    return [json.loads(line.split("typesafe-side: ", 1)[1])
            for line in docker("logs", container, check=False).stdout.splitlines()
            if line.startswith("typesafe-side: ")]


# The mock side ends a run when the scripted reply reaches the channel or it gives up waiting. The
# agent's loop never ends by itself, so an agent that stops first has failed, and the check stops
# waiting then rather than at the mock side's limits.
# Time: one docker wait per container, polled once a second.
# am[verifies a-irp-verify-free-text-1018@908c73]
def first_to_stop(*containers: str) -> tuple[str, int]:
    """The first of the containers to stop and its exit status."""

    waits = {container: subprocess.Popen(["docker", "wait", container], stdout=subprocess.PIPE, text=True)
             for container in containers}
    try:
        while True:
            for container, wait in waits.items():
                if wait.poll() is not None:
                    return container, int(wait.stdout.read().strip() or "1")
            time.sleep(1)
    finally:
        for wait in waits.values():
            if wait.poll() is None:
                wait.terminate()
                wait.wait()


# The MeTTa string literal opening at line[start], unescaped, and the index after it: PeTTa prints a
# string with a backslash before each quote and backslash in it.
# Time: one pass over the literal.
# am[verifies a-irp-verify-free-text-1018@908c73]
def metta_string(line: str, start: int) -> tuple[str, int]:
    text, index = [], start + 1
    while line[index] != '"':
        if line[index] == "\\":
            index += 1
        text.append(line[index])
        index += 1
    return "".join(text), index + 1


# Omega's loop logs each command it ran at INFO as
#   (COMMAND_RETURN: ((goalchainer-request "<request>") "SUCCESS, RETURN: ['<answer>']"))
# with the skill's return value a Python list's repr inside the second string. A failed command logs
# its error in that place instead, and answers nothing here.
# Time: one pass over the log.
# am[verifies a-irp-verify-free-text-1018@908c73]
def request_answers(log: str) -> dict[str, dict]:
    """The JSON answer of each goalchainer-request the loop ran, by its request's review_id."""

    found: dict[str, dict] = {}
    opening = '(COMMAND_RETURN: ((goalchainer-request "'
    for line in log.splitlines():
        start = line.find(opening)
        if start < 0:
            continue
        request, after = metta_string(line, start + len(opening) - 1)
        returned, _ = metta_string(line, line.index('"', after))
        prefix = "SUCCESS, RETURN: "
        if returned.startswith(prefix):
            found[json.loads(request)["context"]["review_id"]] = json.loads(ast.literal_eval(returned[len(prefix):])[0])
    return found


# How many processes the user runs in the container, how many of their environments the scan could
# read through /proc, and how many hold TEXT; None when the scan cannot run, as in a container that
# has stopped. Docker gives root no CAP_SYS_PTRACE, which reading another user's environ takes, so
# the scan runs as that user, under env -i, so its own processes hold nothing the scan looks for.
# am[verifies a-irp-verify-free-text-1018@908c73]
def holders(container: str, user: str, text: str) -> tuple[int, int, int] | None:
    count = ('n=0; r=0; k=0; for p in /proc/[0-9]*; do [ "$(stat -c %U "$p" 2>/dev/null)" = "$1" ] || continue; '
             'n=$((n+1)); cat "$p/environ" >/dev/null 2>&1 || continue; r=$((r+1)); '
             'grep -q -a -F -e "$2" "$p/environ" 2>/dev/null && k=$((k+1)); done; echo "$n $r $k"')
    scanned = docker("exec", "--user", user, container, "env", "-i", "/bin/sh", "-c", count, "sh", user, text,
                     check=False)
    if scanned.returncode != 0:
        return None
    processes, readable, holding = scanned.stdout.split()
    return int(processes), int(readable), int(holding)


# The agent runs as upstream's launcher (scripts/omega start) runs it, with a run-specific name and
# no named memory volume, so a check never touches another container or memory. The terminal -it
# gives is what nginx, running as www-data in the tty group, writes its log to; without it
# /dev/stderr is root's pipe and the entrypoint stops at nginx. The key scan reads the agent's
# processes, run as nobody, while the agent still runs; its OMEGA_DIR, which the entrypoint's
# allowlist keeps, shows the scan can see their environments at all. The containers and the network
# go however the run ends, after their output is kept.
# am[verifies a-oc-plugin-stock-start-1018@f9e0a5] am[implements a-oc-check-mock-in-container-1018@7185d3]
# am[verifies a-irp-verify-free-text-1018@908c73]
def run(image: str, session: str, name: str, volume: str, output: dict[str, str]) -> tuple[list[str], dict[str, dict]]:
    """The reasons NAME's run failed and the answers its agent logged; every container's output goes
    to output[NAME], whether the run finishes or fails."""

    tag = f"{session}-{name}"
    network, agent = f"goalchainer-check-{tag}", f"goalchainer-omega-check-{tag}"
    mock, standin = f"goalchainer-mock-{tag}", f"goalchainer-typesafe-{tag}"
    key = f"fake-typesafe-key-{tag}"
    reasons: list[str] = []
    docker("network", "create", network)
    try:
        start_standin(image, network, standin, volume, "trusted")
        docker("run", "-d", "--name", mock, "--network", network, "--entrypoint", "python3", image,
               "/opt/goalchainer/scripts/check-omega-image.py", "--mock-side", tag, name)
        environment = ["-e", f"TEST_SERVER_IP={mock}", "-e", "IMPORT_KB_ON_START=0", "-e", "HF_HUB_OFFLINE=1",
                       "-e", f"TYPESAFE_UPSTREAM_URL={UPSTREAM}", "-e", f"TYPESAFE_TRUSTED_CERTIFICATE={TLS_DIR}/ca.pem"]
        if RUNS[name]["key"]:
            environment += ["-e", f"TYPESAFE_API_KEY={key}"]
        docker("run", "-d", "-it", "--name", agent, "--network", network,
               "--security-opt", "no-new-privileges:true", "--init",
               "--tmpfs", "/tmp:size=64m,mode=1777", "--tmpfs", "/var/tmp:size=64m,mode=1777",
               "--tmpfs", "/run:size=16m,mode=755", "-v", f"{volume}:{TLS_DIR}:ro", *environment,
               image,
               "commchannel=test", "provider=Test", "embeddingprovider=Local",
               "securityPolicyPath=/PeTTa/repos/Omega/profile/policy.yaml",
               f"TEST_SERVER_IP={mock}", *RUNS[name]["arguments"])
        stopped, status = first_to_stop(mock, agent)
        if stopped == agent:
            reasons.append(f"the agent stopped with status {status} before the mock side finished")
        elif status != 0:
            reasons.append(f"the mock side exited {status}")
        logged = docker("logs", agent, check=False)
        found = request_answers(logged.stdout + logged.stderr)
        for call in RUNS[name]["calls"]:
            answer = found.get(call["context"]["review_id"])
            if answer is None or answer.get("protocol") != "goalchainer-request-v1":
                reasons.append(f"the agent logged no goalchainer-request-v1 answer to {call['context']['review_id']}")
            elif "reading" in call and not answer.get("reading", {}).get("choices"):
                reasons.append(f"the answer to {call['context']['review_id']} carries no reading of its text")
        asked = asked_of(standin)
        if not RUNS[name]["key"] and asked:
            reasons.append(f"the offline run asked TypeSafe {len(asked)} times")
        if RUNS[name]["key"]:
            if not asked:
                reasons.append("the gateway run asked TypeSafe nothing")
            wrong = [seen for seen in asked
                     if (seen["method"], seen["path"], seen["authorization"], seen.get("missing"))
                     != ("POST", "/v1/systemone", f"Bearer {key}", [])]
            if wrong:
                reasons.append(f"TypeSafe got requests other than /v1/systemone with the gateway's key: {wrong}")
        if RUNS[name]["key"] and stopped != agent:
            keyed, seen = holders(agent, "nobody", key), holders(agent, "nobody", "OMEGA_DIR=")
            if keyed is None or seen is None:
                reasons.append("the key scan could not run in the agent's container")
            elif keyed[0] == 0 or keyed[1] != keyed[0] or seen[2] == 0:
                reasons.append(f"the key scan read {keyed[1]} of {keyed[0]} environments, {seen[2]} with OMEGA_DIR")
            elif keyed[2]:
                reasons.append(f"{keyed[2]} of the agent's {keyed[0]} processes hold the key")
        return reasons, found
    finally:
        try:
            parts = []
            for container in (standin, mock, agent):
                result = docker("logs", container, check=False)
                parts.append(f"===== {container}\n{result.stdout}{result.stderr}")
            output[name] = "\n".join(parts)
        finally:
            docker("rm", "-f", standin, mock, agent, check=False)
            docker("network", "rm", network, check=False)


# The gateway alone, started as the entrypoint starts it: the upstream URLs the entrypoint exports
# with its placeholder values, which upstream's other routes need to load, taken from the image's own
# entrypoint.sh, then nginx.sh as www-data, with the terminal its log needs. It is asked once through
# the route for /v1/models with the placeholder key a skill sends, and the status it answers printed.
# A refused upstream is never sent the request, so its stand-in prints nothing.
# am[verifies a-integrate-gateway-tls-verification-1018@ace531]
GATEWAY_PROBE = r"""set -euo pipefail
placeholders="$(grep -E '^[A-Z_]+="[^"]*" # dummy value$' "$OMEGA_DIR/entrypoint.sh")"
eval "$(printf '%s\n' "$placeholders" | sed 's/^/export /')"
su www-data -s /bin/sh -c 'sh /opt/nginx/nginx.sh'
exec python3 - <<'PY'
import time, urllib.error, urllib.request
request = urllib.request.Request("http://127.0.0.1:8080/typesafe/v1/models", headers={"Authorization": "Bearer omega-gateway"})
for attempt in range(50):
    try:
        print("gateway-answered:", urllib.request.urlopen(request, timeout=15).status, flush=True)
        break
    except urllib.error.HTTPError as error:
        print("gateway-answered:", error.code, flush=True)
        break
    except OSError:
        time.sleep(0.2)
else:
    print("gateway-answered: nothing", flush=True)
PY
"""


# One gateway case: a stand-in holding the case's certificate, and the image's gateway trusting the
# test CA. The trusted stand-in must be asked exactly once, with the container's key in place of the
# placeholder; a refused one must be asked nothing while the gateway answers 502 and logs why.
# am[verifies a-integrate-gateway-tls-verification-1018@ace531] am[rests-on c-irp-nginx-upstream-verify-1018@271329]
def gateway_case(image: str, session: str, case: str, volume: str, output: dict[str, str]) -> list[str]:
    certificate, status, refusal = CASES[case]
    tag = f"{session}-{case}"
    network, standin = f"goalchainer-check-{tag}", f"goalchainer-typesafe-{tag}"
    key = f"fake-typesafe-key-{tag}"
    reasons: list[str] = []
    probed: subprocess.CompletedProcess[str] | None = None
    docker("network", "create", network)
    try:
        start_standin(image, network, standin, volume, certificate)
        probed = docker("run", "--rm", "-t", "--network", network, "-v", f"{volume}:{TLS_DIR}:ro",
                        "-e", f"TYPESAFE_API_KEY={key}", "-e", f"TYPESAFE_UPSTREAM_URL={UPSTREAM}",
                        "-e", f"TYPESAFE_TRUSTED_CERTIFICATE={TLS_DIR}/ca.pem",
                        "--entrypoint", "bash", image, "-c", GATEWAY_PROBE, check=False)
        shown = probed.stdout.replace("\r", "")
        answered = [line.split(":", 1)[1].strip() for line in shown.splitlines() if line.startswith("gateway-answered:")]
        asked = asked_of(standin)
        if answered != [str(status)]:
            reasons.append(f"the gateway answered {answered or 'nothing'}, not {status}")
        if refusal is None:
            if [(seen["method"], seen["path"], seen["authorization"]) for seen in asked] \
                    != [("GET", "/v1/models", f"Bearer {key}")]:
                reasons.append(f"the trusted stand-in was asked {asked}, not once with the container's key")
        else:
            if asked:
                reasons.append(f"the gateway sent {len(asked)} requests to a stand-in it should refuse")
            if refusal not in shown:
                reasons.append(f"nginx logged no '{refusal}'")
        return reasons
    finally:
        try:
            stand = docker("logs", standin, check=False)
            output[case] = f"===== gateway {tag}\n{probed.stdout if probed else ''}\n" \
                           f"===== {standin}\n{stand.stdout}{stand.stderr}"
        finally:
            docker("rm", "-f", standin, check=False)
            docker("network", "rm", network, check=False)


# An answer without its inference counts. A count measures the engine's work, not the answer, and it
# differs by one between processes answering one request with the same readings (two image runs:
# 1254566 and 1254567), so the two runs' answers agree on every other field.
# Time: one pass over the answer.
# am[verifies a-irp-verify-free-text-1018@908c73] am[rests-on c-irp-inference-count-varies-1018@ff0f84]
def without_counts(value: object) -> object:
    if isinstance(value, dict):
        return {key: without_counts(item) for key, item in value.items() if key != "inferences"}
    if isinstance(value, list):
        return [without_counts(item) for item in value]
    return value


# The native wheels the image installed, checked after every later build step as the build checked
# them right after uv sync: the directories this checkout's lock names, verified by place here, are
# mounted read-only where the image's lock names them, and the image's environment runs its own copy
# of the verifier's check against them. root runs it, since the store's files may be readable by
# their owner alone. Its identity line, the wheel, its digest and its engine's, goes to the log.
# am[verifies a-irp-image-native2-wheel-1018@ec11d2] am[rests-on c-irp-n2-source-immaterial-1018@63bd66]
def native_identity(image: str, output: dict[str, str]) -> list[str]:
    placed = subprocess.run(["uv", "run", "--quiet", str(REPO / "scripts" / "native-wheels.py"), "place"],
                            cwd=REPO, capture_output=True, text=True, check=False)
    if placed.returncode != 0:
        output["native-wheels"] = f"===== native-wheels place\n{placed.stdout}{placed.stderr}"
        return [f"place exited {placed.returncode}: {placed.stderr.strip()}"]
    mounts = [argument for directory in placed.stdout.splitlines()
              for argument in ("-v", f"{(REPO / directory).resolve()}:/opt/goalchainer/{directory}:ro")]
    checked = docker("run", "--rm", "--user", "0:0", *mounts, "--entrypoint", "/opt/goalchainer/.venv/bin/python",
                     image, "-I", "/opt/goalchainer/scripts/native-wheels.py", "check", check=False)
    output["native-wheels"] = f"===== native-wheels check\n{checked.stdout}{checked.stderr}"
    if checked.returncode != 0:
        return [f"check exited {checked.returncode}: {checked.stderr.strip()}"]
    if not checked.stdout.startswith("native-wheels: "):
        return [f"check printed no identity line: {checked.stdout.strip()!r}"]
    return []


# The runs and the gateway's cases go side by side, each on its own network, after the TLS material is
# made in its volume, which goes with the check. The two answers to the same text must agree: replay
# through the gateway gives the reader the answers it replays offline, so any difference is the
# gateway's or the configuration's. The native wheel check goes beside them.
# Time: the slowest of the two runs, each one agent start plus its skill calls, the three cases and
# the native wheel check, one sha256 pass over pymetta's installed files.
# am[verifies a-oc-plugin-stock-start-1018@f9e0a5] am[verifies a-irp-verify-free-text-1018@908c73]
# am[rests-on 060aea0d@012966] am[verifies a-integrate-gateway-tls-verification-1018@ace531]
# am[verifies a-irp-image-native2-wheel-1018@ec11d2]
def main(image: str, log: Path) -> int:
    session = uuid.uuid4().hex[:8]
    volume = f"goalchainer-check-tls-{session}"
    output: dict[str, str] = {}
    docker("volume", "create", volume)
    try:
        docker("run", "--rm", "-v", f"{volume}:{TLS_DIR}", "--entrypoint", "bash", image,
               "-c", TLS_MATERIAL, "tls", TLS_DIR)
        with ThreadPoolExecutor(len(RUNS) + len(CASES) + 1) as pool:
            runs = {name: pool.submit(run, image, session, name, volume, output) for name in RUNS}
            cases = {case: pool.submit(gateway_case, image, session, case, volume, output) for case in CASES}
            native = pool.submit(native_identity, image, output)
            results = {name: future.result() for name, future in runs.items()}
            refused = {case: future.result() for case, future in cases.items()}
            unverified = native.result()
    finally:
        log.write_text("\n".join(output[name] for name in (*RUNS, *CASES, "native-wheels") if name in output),
                       encoding="utf-8")
        docker("volume", "rm", "-f", volume, check=False)
    failures = [f"{name}: {reason}" for name, (reasons, _) in results.items() for reason in reasons]
    failures += [f"gateway {case}: {reason}" for case, reasons in refused.items() for reason in reasons]
    failures += [f"native wheels: {reason}" for reason in unverified]
    offline, gateway = (results[name][1].get(READING["context"]["review_id"]) for name in ("offline", "gateway"))
    if offline is not None and gateway is not None and without_counts(offline) != without_counts(gateway):
        failures.append("the gateway run's answer to the text differs from the offline run's")
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        print(f"see {log}", file=sys.stderr)
        return 1
    print("offline: goalchainer-request read the text from the replay cache with no key, through Omega's loop",
          flush=True)
    print("gateway: the fake key reached TypeSafe over verified TLS only as the gateway's bearer token, no agent "
          "process held it, and the answer equals the offline one", flush=True)
    print("gateway cases: a trusted certificate was forwarded to with the key; a rogue CA's and a wrong host's "
          "were refused with 502 before any request reached them", flush=True)
    print(output["native-wheels"].splitlines()[1], flush=True)
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--mock-side":
        sys.exit(mock_side(sys.argv[2], sys.argv[3]))
    if sys.argv[1:] == ["--typesafe-side"]:
        sys.exit(typesafe_side())
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    sys.exit(main(sys.argv[1], Path(sys.argv[2]).resolve()))
