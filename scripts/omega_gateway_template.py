#!/usr/bin/env python3
"""Purpose: write Omega's gateway template with a /typesafe/ route added to upstream's, and refuse
unless upstream's own nginx.sh renders that template with the route's variables substituted.

    scripts/omega_gateway_template.py PROXY OUTPUT

PROXY is a directory holding upstream's nginx.sh and nginx.conf.template: the pinned
external/OmegaClaw-Core/proxy, or /opt/nginx in the image, where they are the files the gateway
starts from. OUTPUT is where the derived template goes; the image names it to nginx.sh with
NGINX_TEMPLATE. The route forwards http://localhost:8080/typesafe/ to TYPESAFE_UPSTREAM_URL with
TYPESAFE_API_KEY as the bearer token, as upstream's routes do for each provider, so the key stays in
the gateway and never reaches the agent. Unlike upstream's routes, it sends the key only to a server
whose certificate chains to the CA certificates in TYPESAFE_TRUSTED_CERTIFICATE and names the
upstream's host.

Before writing, the derived template is rendered by upstream's nginx.sh itself, with a stand-in nginx
and probe values for the route's variables. The output is written only when that rendering holds the
route with every value in place, so a pin whose nginx.sh ignores NGINX_TEMPLATE or substitutes other
names fails the build here instead of shipping a gateway without the route.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path

# The route joins upstream's server block on port 8080. Its shape is upstream's /openaiapi/ route,
# whose upstream is also a template variable, so nginx's default Host and SNI name are the
# upstream's own host. The reader bounds each Jev request at 10 s, inside the http block's proxy
# timeouts, so the route sets none.
# Its trust is its own, set inside the location so upstream's routes are untouched: nginx sends the
# request only after the upstream's chain verifies against the CA certificates the route names and
# its certificate names the proxy_pass host, which nginx checks by default once verification is on;
# otherwise it answers 502 and the key never leaves. The depth is OpenSSL's own default of 100
# intermediates, the limit the SDK applies when it calls the service directly, so the gateway refuses
# no chain the SDK would accept.
# am[implements a-irp-template-generator-1018@7b88ae] am[rests-on c-irp-omega-secrets-in-gateway-1018@8a5f0a]
# am[rests-on c-irp-sdk-gateway-compatible-1018@2b8203] am[rests-on c-irp-route-host-default-1018@f71bbc]
# am[rests-on c-irp-route-timeouts-inherited-1018@02a6a7] am[addresses i-irp-gateway-tls-unverified-1018@65fb36]
# am[implements a-integrate-gateway-tls-verification-1018@ace531] am[rests-on c-integrate-gateway-local-tls-verification-1018@1b37ab]
# am[rests-on c-irp-nginx-upstream-verify-1018@271329] am[rests-on c-irp-verify-depth-client-default-1018@8b2f61]
ROUTE = """\
location /typesafe/ {
    proxy_pass ${TYPESAFE_UPSTREAM_URL};
    proxy_set_header Authorization "Bearer ${TYPESAFE_API_KEY}";
    proxy_ssl_server_name on;
    proxy_ssl_protocols TLSv1.2 TLSv1.3;
    proxy_ssl_verify on;
    proxy_ssl_trusted_certificate ${TYPESAFE_TRUSTED_CERTIFICATE};
    proxy_ssl_verify_depth 100;
    proxy_http_version 1.1;
}
"""
LISTEN = "listen 8080;"

# Values the guard renders with. The .invalid name never resolves (RFC 6761) and nginx never starts,
# so nothing is contacted.
# am[implements a-irp-template-generator-1018@7b88ae]
PROBE = {"TYPESAFE_UPSTREAM_URL": "https://gateway-probe.invalid/", "TYPESAFE_API_KEY": "gateway-probe-key",
         "TYPESAFE_TRUSTED_CERTIFICATE": "/gateway-probe/ca.pem"}


# am[implements a-irp-template-generator-1018@7b88ae]
class GatewayTemplateError(Exception):
    """Upstream's gateway no longer offers what the route relies on; the message says what moved."""


# A template that already mentions TypeSafe means upstream took the service up itself, so a second
# route would collide with its own; one without exactly one listen line has no single server block
# for the route to join.
# Time: one pass over the template's lines.
# am[implements a-irp-template-generator-1018@7b88ae]
def derive(template: str) -> tuple[str, str]:
    """Upstream's template with ROUTE inserted after its one `listen 8080;` line, indented as that
    line is, and the inserted block. Raises GatewayTemplateError when the template mentions TypeSafe
    already or has no such line or more than one."""

    lines = template.splitlines(keepends=True)
    mentions = [number for number, line in enumerate(lines, 1) if "typesafe" in line.lower()]
    if mentions:
        raise GatewayTemplateError(
            f"upstream's nginx.conf.template already mentions TypeSafe on lines {mentions}; "
            "reconcile its route with this one")
    anchors = [index for index, line in enumerate(lines) if line.strip() == LISTEN]
    if len(anchors) != 1:
        raise GatewayTemplateError(
            f"upstream's nginx.conf.template has {len(anchors)} '{LISTEN}' lines, "
            "not the one server block the route joins")
    (anchor,) = anchors
    indent = lines[anchor][: len(lines[anchor]) - len(lines[anchor].lstrip())]
    block = "\n" + "".join(indent + line for line in ROUTE.splitlines(keepends=True))
    return "".join(lines[: anchor + 1]) + block + "".join(lines[anchor + 1 :]), block


# am[implements a-irp-template-generator-1018@7b88ae]
def substitute(text: str, values: Mapping[str, str]) -> str:
    """TEXT with each ${NAME} in VALUES replaced by its value, as envsubst replaces it."""

    for name, value in values.items():
        text = text.replace("${" + name + "}", value)
    return text


# nginx.sh ends by starting nginx, so a stand-in that exits 0 comes first on PATH. The environment
# holds nothing else, so every name the template mentions and VALUES lacks renders empty, whatever
# the caller's environment holds.
# Time: one sh run of nginx.sh: grep, sort, tr and envsubst over the template.
# am[implements a-irp-template-generator-1018@7b88ae] am[rests-on c-irp-nginx-template-knob-1018@664b20]
def render(proxy: Path, template: Path, values: Mapping[str, str], workdir: Path) -> str:
    """The configuration PROXY's nginx.sh writes when NGINX_TEMPLATE names TEMPLATE and VALUES are
    the only variables set. Scratch files go in a directory under WORKDIR, removed afterwards.
    Raises GatewayTemplateError when nginx.sh fails."""

    with tempfile.TemporaryDirectory(dir=workdir, prefix=".gateway-") as scratch:
        stand_in = Path(scratch) / "bin" / "nginx"
        stand_in.parent.mkdir()
        stand_in.write_text("#!/bin/sh\nexit 0\n")
        stand_in.chmod(0o755)
        config = Path(scratch) / "nginx.conf"
        environment = {
            "PATH": f"{stand_in.parent}{os.pathsep}{os.environ.get('PATH', os.defpath)}",
            "NGINX_TEMPLATE": str(template),
            "NGINX_CONFIG": str(config),
            **values,
        }
        script = proxy / "nginx.sh"
        completed = subprocess.run(["sh", str(script)], env=environment, capture_output=True, text=True,
                                   check=False)
        if completed.returncode != 0:
            raise GatewayTemplateError(
                f"{script} exited {completed.returncode} rendering {template}: {completed.stderr.strip()}")
        return config.read_text()


# The rendered route tells apart the two ways nginx.sh can move: no route at all means it rendered a
# template other than the one NGINX_TEMPLATE named; a route still holding ${...} means it no longer
# substitutes those names.
# Time: one render, plus linear passes over the template.
# am[implements a-irp-template-generator-1018@7b88ae] am[rests-on c-irp-nginx-template-knob-1018@664b20]
def write(proxy: Path, output: Path) -> None:
    """Write the derived template to OUTPUT once PROXY's nginx.sh renders it with the route's
    variables substituted. Raises GatewayTemplateError, leaving OUTPUT untouched, otherwise."""

    derived, block = derive((proxy / "nginx.conf.template").read_text())
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".gateway-") as scratch:
        candidate = Path(scratch) / output.name
        candidate.write_text(derived)
        rendered = render(proxy, candidate, PROBE, Path(scratch))
        if substitute(block, PROBE) not in rendered:
            if "location /typesafe/" not in rendered:
                moved = "rendered a template other than the one NGINX_TEMPLATE named"
            elif block in rendered:
                moved = "left ${TYPESAFE_UPSTREAM_URL} and ${TYPESAFE_API_KEY} unsubstituted"
            else:
                moved = "rendered the route other than as written"
            raise GatewayTemplateError(f"upstream's {proxy / 'nginx.sh'} {moved}")
        os.replace(candidate, output)


# am[implements a-irp-template-generator-1018@7b88ae]
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write Omega's gateway template with a /typesafe/ route added to upstream's.")
    parser.add_argument("proxy", type=Path, help="directory holding upstream's nginx.sh and nginx.conf.template")
    parser.add_argument("output", type=Path, help="where the derived template is written")
    args = parser.parse_args(argv)
    try:
        write(args.proxy, args.output)
    except (GatewayTemplateError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"wrote {args.output}: upstream's {args.proxy / 'nginx.conf.template'} with a /typesafe/ route")
    return 0


if __name__ == "__main__":
    sys.exit(main())
