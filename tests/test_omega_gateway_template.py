"""Purpose: verify scripts/omega_gateway_template.py derives Omega's gateway template from the pinned
commit's own with exactly one /typesafe/ route added, which verifies its upstream's certificate
against the CA file it names, that upstream's nginx.sh renders it with a fake key, a local upstream
and a test CA in place and every other line as upstream renders its own, and that it refuses, writing
nothing, each way upstream's gateway interface can move. scripts/check-omega-image.py proves the
verification itself on the image's nginx."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GENERATOR = REPO / "scripts" / "omega_gateway_template.py"
CORE = REPO / "external" / "OmegaClaw-Core"

_spec = importlib.util.spec_from_file_location("omega_gateway_template", GENERATOR)
gateway = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gateway)

FAKE = {"TYPESAFE_API_KEY": "fake-typesafe-key", "TYPESAFE_UPSTREAM_URL": "https://typesafe.test:18443/",
        "TYPESAFE_TRUSTED_CERTIFICATE": "/opt/test-ca/ca.pem"}


# The pinned commit's proxy files as committed, whatever the submodule's working tree holds.
# am[verifies a-irp-template-generator-1018@7b88ae]
@pytest.fixture
def proxy(tmp_path: Path) -> Path:
    pin = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD:external/OmegaClaw-Core"],
                         check=True, capture_output=True, text=True).stdout.strip()
    directory = tmp_path / "proxy"
    directory.mkdir()
    for name in ("nginx.sh", "nginx.conf.template"):
        (directory / name).write_bytes(subprocess.run(["git", "-C", str(CORE), "show", f"{pin}:proxy/{name}"],
                                                      check=True, capture_output=True).stdout)
    return directory


# Removing the one inserted block gives upstream's template back byte for byte, so every upstream
# line survives in order and nothing else changed.
# am[verifies a-irp-template-generator-1018@7b88ae]
def test_the_derived_template_is_upstreams_with_one_route_after_its_listen_line(proxy):
    template = (proxy / "nginx.conf.template").read_text()
    derived, block = gateway.derive(template)

    assert derived.replace(block, "", 1) == template
    assert derived.count("location /typesafe/") == 1
    listen = "        listen 8080;\n"
    assert derived.index(block) == derived.index(listen) + len(listen)
    assert "\n        location /typesafe/ {\n            proxy_pass ${TYPESAFE_UPSTREAM_URL};\n" in block


# The route sends the key only to an upstream nginx has verified: the chain against the CA file the
# route names, at OpenSSL's default depth, and the certificate's name against the proxy_pass host,
# which nginx checks by default once verification is on.
# am[verifies a-integrate-gateway-tls-verification-1018@ace531]
def test_the_route_verifies_its_upstream_against_the_ca_file_it_names(proxy):
    _, block = gateway.derive((proxy / "nginx.conf.template").read_text())

    lines = [line.strip() for line in block.splitlines()]
    assert "proxy_ssl_verify on;" in lines
    assert "proxy_ssl_trusted_certificate ${TYPESAFE_TRUSTED_CERTIFICATE};" in lines
    assert "proxy_ssl_verify_depth 100;" in lines
    assert "proxy_ssl_server_name on;" in lines
    assert not any(line.startswith("proxy_ssl_name") for line in lines)


# Rendering commutes with deriving: upstream's nginx.sh renders the derived template exactly as it
# renders upstream's own with the route added after, the fake key in the route's Authorization
# header, the local upstream in its proxy_pass and the test CA as its trusted certificates.
# Time: three sh runs of nginx.sh over the gateway template.
# am[verifies a-irp-template-generator-1018@7b88ae] am[verifies a-integrate-gateway-tls-verification-1018@ace531]
def test_upstreams_nginx_sh_renders_the_route_with_a_fake_key_and_a_local_upstream(proxy, tmp_path):
    output = tmp_path / "gateway" / "goalchainer.conf.template"
    output.parent.mkdir()
    gateway.write(proxy, output)

    ours = gateway.render(proxy, output, FAKE, tmp_path)
    upstream, block = gateway.derive(gateway.render(proxy, proxy / "nginx.conf.template", FAKE, tmp_path))

    assert ours == upstream.replace(block, gateway.substitute(block, FAKE), 1)
    assert '            proxy_set_header Authorization "Bearer fake-typesafe-key";\n' in ours
    assert "            proxy_pass https://typesafe.test:18443/;\n" in ours
    assert "            proxy_ssl_trusted_certificate /opt/test-ca/ca.pem;\n" in ours
    assert "${" not in gateway.substitute(block, FAKE)
    assert sorted(path.name for path in output.parent.iterdir()) == ["goalchainer.conf.template"]


# Each case moves one part of the interface the route relies on, in a copy of the pinned files, and
# gives a pattern for what the refusal must say moved; <proxy> stands for the copy's directory.
MOVES = {
    "nginx.sh reads a fixed template": (
        "nginx.sh", "NGINX_TEMPLATE=${NGINX_TEMPLATE:-/opt/nginx/nginx.conf.template}",
        "NGINX_TEMPLATE=<proxy>/nginx.conf.template",
        "rendered a template other than the one NGINX_TEMPLATE named"),
    "nginx.sh substitutes only letters": (
        "nginx.sh", "[A-Z_0-9]", "[A-Z]", "unsubstituted"),
    "nginx.sh copies the template as it is": (
        "nginx.sh", 'envsubst "$SUBST_VARS" \\', "cat \\", "unsubstituted"),
    "nginx.sh no longer reads its template": (
        "nginx.sh", '< "${NGINX_TEMPLATE}"', "< <proxy>/missing.template", "exited [1-9]"),
    "the template listens on another port": (
        "nginx.conf.template", "listen 8080;", "listen 9090;", "has 0 'listen 8080;' lines"),
    "the template has two servers on 8080": (
        "nginx.conf.template", "listen 8080;", "listen 8080;\n    }\n    server {\n        listen 8080;",
        "has 2 'listen 8080;' lines"),
    "the template routes TypeSafe already": (
        "nginx.conf.template", "location /health {", "location /typesafe/ {\n        }\n\n        location /health {",
        "already mentions TypeSafe"),
}


# am[verifies a-irp-template-generator-1018@7b88ae]
@pytest.mark.parametrize("move", MOVES)
def test_a_moved_interface_is_refused_and_nothing_is_written(proxy, tmp_path, move):
    name, old, new, pattern = MOVES[move]
    original = (proxy / name).read_text()
    assert original.count(old) == 1
    (proxy / name).write_text(original.replace(old, new.replace("<proxy>", str(proxy))))
    output = tmp_path / "gateway" / "goalchainer.conf.template"
    output.parent.mkdir()

    with pytest.raises(gateway.GatewayTemplateError, match=pattern):
        gateway.write(proxy, output)
    assert list(output.parent.iterdir()) == []


# The command line reports a refusal or a missing file as one error line with status 1, and a
# derivation with status 0.
# am[verifies a-irp-template-generator-1018@7b88ae]
def test_the_command_reports_refusals_with_status_one(proxy, tmp_path):
    output = tmp_path / "goalchainer.conf.template"
    command = [sys.executable, "-I", str(GENERATOR), str(proxy), str(output)]

    written = subprocess.run(command, capture_output=True, text=True, check=False)
    assert (written.returncode, written.stderr) == (0, "")
    assert output.read_text() == gateway.derive((proxy / "nginx.conf.template").read_text())[0]

    output.unlink()
    template = proxy / "nginx.conf.template"
    template.write_text(template.read_text().replace("listen 8080;", "listen 9090;"))
    refused = subprocess.run(command, capture_output=True, text=True, check=False)
    assert refused.returncode == 1
    assert refused.stderr.startswith("error: upstream's nginx.conf.template has 0 'listen 8080;' lines")
    assert not output.exists()

    template.unlink()
    missing = subprocess.run(command, capture_output=True, text=True, check=False)
    assert missing.returncode == 1
    assert missing.stderr.startswith("error: [Errno 2] No such file or directory")
