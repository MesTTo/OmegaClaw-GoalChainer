# GoalChainer plugin

The plugin exposes domain review, planning and current-step admission through
the operator's MesTTo/MeTTa engine via pymetta. A request selects its domain and
supplies evidence, a reference time and resource limits. Optional text is read
against that domain's declared propositions.

<!-- am[implements a-integrate-domain-surface-1018@759698] -->
<!-- am[implements a-v2-cli-skill-surface-1020@6f755c] -->

## Skills

| Skill | Input and result |
| --- | --- |
| `goalchainer-request json_request` | A selected domain, context and `review`, `plan` or `admit` operation; returns the review and any planning or admission result. |
| `goalchainer-directive-dispatch json_request` | An explicit durable-plan operation, such as status, claim or complete. |
| `goalchainer-snars-dispatch json_request` | An explicit evidence, proof, condition, obligation, counterfactual or trust operation. |
| `goalchainer-motivation-dispatch json_request` | Record need observations or host-reported attempts, or inspect the current motivational snapshot. |

The prompt extension describes the same operations. Every reasoning request
requires a positive integer `inference_budget` and a finite positive
`timeout_seconds`. These limits create one budget shared by all request stages.
Exhaustion returns a typed error.

For a domain review, pass this JSON as the string argument to
`goalchainer-request`:

```json
{
  "operation": "review",
  "domain": {"packaged": "incident"},
  "context": {
    "review_id": "incident-42",
    "subject": "checkout",
    "trigger": "incident-report",
    "as_of": "2026-10-16T09:00:00+00:00",
    "authority": "advisory",
    "policy_version": "incident-v1",
    "readings": []
  },
  "reading": {
    "text": "Raw logs include customer emails. Engineering needs the incident room.",
    "observed_at": "2026-10-16T09:00:00+00:00",
    "valid_until": null
  },
  "inference_budget": 1000000000,
  "timeout_seconds": 600
}
```

Keep the user's text unchanged in `reading.text`. The limits above are example
allowances. `domain` selects exactly one packaged name or file path.
`context.readings` can supply attributed observations without text. Text is
refused when the selected domain has no reading declaration.

The result preserves the complete structured review. Planning can return a
plan, an inquiry or an exhausted-space `NoPlan`; admission can report admitted,
blocked, ambiguous or stale. None grants execution authority or confirms a
host effect. The host must supply its authorization and subsequent receipt.

For a domain declaring needs, the review request can also select a motivation
stream with `"motivation": {"store": "/path/to/needs.db", "stream": "companion"}`.
Use `goalchainer-motivation-dispatch` with an `observe`, `attempt` or `status`
operation to maintain that stream. An observation reports a measured need level;
an attempt reports what the host tried and when it applied it. A review records
neither. The [motivation guide](../../docs/motivation.md) gives the domain forms,
request fields and a worked sequence.

The CLI accepts the same operation object from a file or standard input:

```sh
goalchainer motivation --input request.json --inference-budget 1000000000 --timeout-seconds 600
```

Its output is JSON, including typed errors. `goalchainer show` renders a saved
review request's need levels, predicted changes and reasons for holding. A
prediction is not an observed outcome, and a hold grants no execution authority.

Directive and SNARS requests carry the same limits beside their operation
fields. Unknown fields and group-operation mismatches are refused. For example:

```metta
(goalchainer-directive-dispatch
  "{\"operation\":\"status\",\"plan\":\"/path/to/work.metta\",\"inference_budget\":1000000000,\"timeout_seconds\":600}")
(goalchainer-snars-dispatch
  "{\"group\":\"trust-discovery\",\"operation\":\"inspect\",\"inference_budget\":1000000000,\"timeout_seconds\":600}")
```

<!-- am[implements a-ie-sr-select-domain-1018@577734] -->
A SNARS request that gives text in `request` selects the domain it is read with as a
`goalchainer-request` does, `"domain": {"packaged": "incident"}` or
`"domain": {"path": "/path/to/domain.metta"}`. Text with no domain is refused, as is a domain
that declares no reading section; an operation on statements alone needs no domain.

## Installation and process boundary

Install GoalChainer's locked environment as the
[README's installation instructions](../../README.md#installation) describe, then the plugin:

```sh
./scripts/setup-omegaclaw.sh
```

The installer copies the plugin and `gcskill.py` into the Omega checkout's
`plugins/goalchainer`, records the interpreter in a generated
`goalchainer_host.py` there and registers the plugin with one record in
`config/plugins.yaml`, through Omega's plugin API. Omega's MeTTa loader puts the
plugin's directory on the agent's `sys.path`, so the agent imports `gcskill` and
reads the recorded interpreter from there with nothing added to its environment.
The installation receipt lists copied and written files;
`./scripts/setup-omegaclaw.sh --uninstall` uses that receipt.

The top-level `gcskill` module starts the recorded interpreter and decodes its
JSON response. It removes the host's `PYTHONPATH`, `PYTHONHOME` and
`SWI_HOME_DIR` from the child's environment. Typed child failures remain typed.
GoalChainer carries its deontic and directive libraries in its own package.

## Running in a container

<!-- am[implements a-irp-image-semantic-1018@5d0f7c] am[implements a-irp-gateway-route-1018@11ed50] am[implements a-irp-verify-free-text-1018@908c73] am[implements a-irp-image-native2-wheel-1018@ec11d2] -->
Omega's image runs the agent on PeTTa. `scripts/build-omega-image.sh` builds an
image from upstream's published `singularitynet/omega` image, pinned by digest.
The image has the pinned Omega source in place of its own, GoalChainer's locked
environment with the `semantic` extra and pymetta's native build, the
cross-encoder revision the gate pins, and this plugin installed. The build takes
both trees from committed revisions, so nothing uncommitted reaches the image:

```sh
./scripts/build-omega-image.sh      # builds goalchainer-omega:<revision>
external/OmegaClaw-Core/scripts/omega start -p <provider> -t <channel> -d goalchainer-omega:<revision>
```

The build needs the native build's directory, as the gate does: it reads it from
the store `GOALCHAINER_NATIVE_WHEELS` names, or from this checkout's
`native-wheels/` when that is unset, and `scripts/native-wheels.py place`
verifies it against its `MANIFEST` before Docker starts. Docker gets a copy as
the named build context `native-wheels`, mounted read-only only while `uv sync`
installs from it, so no wheel stays in the image. Inside the build, `place`
verifies that copy again before uv reads it, and `check` verifies every file uv
installed and prints the wheel and its engine in the build's log. A missing or
changed directory stops the build.

The plugin's reader settings are Omega configuration keys. In the container you
set one as a `key=value` argument after the image name, or in Omega's
`config/config.yaml`. Omega's entrypoint starts the agent with an environment
reduced to an allowlist, so neither `OMEGA_<key>` variables nor the reader's own
`GOALCHAINER_*` variables reach it there.

| Key | Image default | Meaning |
| --- | --- | --- |
| `goalchainerModelCache` | `/opt/goalchainer/models` | the cross-encoder's cache, read-only in the image |
| `goalchainerJevCache` | `/PeTTa/repos/Omega/memory/goalchainer-jev` | the Jev answer cache, kept with Omega's memory |
| `goalchainerJevOffline` | `1` | `1` answers from the cache alone; `0` also asks Jev for what it lacks |
| `goalchainerJevUrl` | `http://localhost:8080/typesafe` | where Jev requests go: Omega's gateway |

The image reads offline by default: text whose answers the cache lacks fails
with `not_cached`, and nothing is sent to TypeSafe. To let the reader ask Jev,
give the container your key and turn the switch. Upstream's launcher passes
neither, so start the container with `docker run` as the launcher's `docker_cmd`
in `scripts/omega` does, adding `-e TYPESAFE_API_KEY` before the image name and
`goalchainerJevOffline=0` after it.

The key reaches only Omega's gateway, as each provider's key does. nginx starts
before the entrypoint reduces the environment, and sets the key as the bearer
token on its `/typesafe/` route; the reader in the agent sends a placeholder in
its place. `TYPESAFE_UPSTREAM_URL`, by default `https://api.typesafe.ai/`, names
the service the route forwards to and must end in `/`. The build generates the
route from upstream's `proxy/nginx.conf.template` with
`scripts/omega_gateway_template.py`, which refuses when upstream's `nginx.sh` no
longer renders the template the image names in `NGINX_TEMPLATE`.

Unlike upstream's routes, `/typesafe/` verifies the server before it sends the
key. The server's certificate must chain to a CA in the file
`TYPESAFE_TRUSTED_CERTIFICATE` names and must name the host in
`TYPESAFE_UPSTREAM_URL`. By default that file is the image's system CA bundle,
the public roots typesafe-sdk itself trusts. Point both variables elsewhere
together, for instance at a TypeSafe endpoint behind your own CA. A server that
fails either check gets no request, and the reader sees the gateway's 502.
Upstream's own routes stay as upstream ships them, without verification.

`scripts/check-omega-image.py IMAGE LOG` starts the image twice with Omega's mock
provider and test channel, as Omega's launcher starts any image. In each run a
second container of the image plays the mock provider and channel, and a third
plays TypeSafe over TLS, answering from the committed replay cache, all on a
private network:

- The offline run keeps the image's defaults and names the committed cache with
  `goalchainerJevCache`. The mock asks for a review without text and one of a
  text the cache answers. It passes when both answers come back through Omega's
  loop, the agent's `send` reaches the channel, and nothing asked TypeSafe.
- The gateway run gives the container a fake `TYPESAFE_API_KEY` and
  `goalchainerJevOffline=0`, with an empty answer cache. It passes when every
  request reaches the stand-in over verified TLS with the fake key as the
  gateway's bearer token, no agent process holds the key, and the answer equals
  the offline run's.

It also starts the image's gateway alone three times against a stand-in that
answers to the same name. The stand-in's certificate is signed by a test CA the
gateway trusts, by a second CA it does not trust, or by the test CA for another
host. The check passes when the trusted stand-in receives one request carrying
the fake key, and the other two receive none while the gateway answers 502 and
logs nginx's refusal. The check makes its CAs and certificates afresh in a
container of the image each time.

Last, it mounts this checkout's verified native build read-only into a container
of the image and runs the image's own `scripts/native-wheels.py check` there.
That checks the image's pymetta file by file against the published wheel after
every later build step, and the check prints the wheel and engine it found.

Both runs point `TYPESAFE_UPSTREAM_URL` at the stand-in and set
`HF_HUB_OFFLINE=1`, so no hosted model or service is called. For the same
reason the check never verifies api.typesafe.ai's own certificate chain against
the image's bundle. That needs a live connection, and nothing here has made one.

## Verification

```sh
OMEGACLAW_DIR=<the checkout> plugins/goalchainer/tests/run.sh
```

<!-- am[implements a-integrate-mettaspeak-assertion-accounting-1019@905c82] -->
A suite passes only when its run exits 0, no check fails, and it reports exactly
as many checks as its source declares `test` forms in its directives, at least
one. `suite_accounting.py` counts those forms with GoalChainer's own form
scanner and parser. A run that stops after a passing prefix fails, even with
status 0, and so does a suite with no `test` form. With no suite to run, the
runner fails rather than passing nothing. Name suites after the script to run
only those.

The registration test imports Omega's skill registry under its `Omega` library
alias, loads the plugin and calls its `loadOmegaPlugin`, then checks that each
skill reaches the model as a tool with one `json_request` parameter and that the
prompt extension is present. Omega's own loader evaluates that entry point from
`&self` after importing the plugin into a space of its own. PeTTa's global rules
let that call reach the plugin; pymetta's rules belong to the space that defines
them, so on pymetta the loader registers nothing and the suite calls the entry
point directly.
The process test runs a domain review through the recorded interpreter, checks
a malformed request's error code and repeats the review with hostile host
runtime variables. The offline replay test derives its texts from those actual
MeTTa call sites.
