# syntax=docker/dockerfile:1.7

# Purpose: build the Omega agent image with GoalChainer's plugin installed: upstream's published Omega
# image, the pinned Omega source in place of the image's own, GoalChainer's locked environment with
# its semantic extra, pymetta from the verified native wheel directory its lock names, and the gate's
# pinned cross-encoder, the plugin registered through Omega's plugin API with its reader offline by
# default, and Omega's gateway with a /typesafe/ route that keeps the TypeSafe key out of the agent.
# scripts/build-omega-image.sh assembles the context from committed trees, goalchainer/ at HEAD and
# omega/ at the external/OmegaClaw-Core pin, and passes the native wheel directories as the named
# context native-wheels.
#
# The base is upstream's newest published image, v0.1.20. Between it and the pin upstream changed
# neither its Dockerfile nor requirements.txt, so the image's runtime, PeTTa and Python packages
# included, is what upstream's Dockerfile builds for the pin; only Omega's own source moved.
# am[implements a-oc-plugin-stock-start-1018@f9e0a5] am[rests-on c-oc-plugin-api-1018@14ec52]
ARG OMEGA_IMAGE=docker.io/singularitynet/omega:v0.1.20@sha256:67bc5843c77b3c5ef4c0d7c8d7eab1c14ee20813e9f7d7c95627e4a1aa016ce7
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.11.19
FROM ${UV_IMAGE} AS uv

# The native wheel directories uv.lock installs from, which no index serves.
# scripts/build-omega-image.sh passes verified copies of them as the named build context
# native-wheels, which replaces this empty stage. A build given none mounts nothing, so the place
# below refuses, naming the directory the lock needs, where Docker would otherwise look for an image
# of that name.
# am[implements a-irp-image-native2-wheel-1018@ec11d2]
FROM scratch AS native-wheels

FROM ${OMEGA_IMAGE}

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Omega's source at the pin replaces the image's, with what upstream's Dockerfile derives from it:
# the baked version file Omega reads without git metadata, the nginx proxy configuration, the
# run.metta PeTTa starts and the scripts' modes.
ARG OMEGA_VERSION
COPY omega/ /opt/omega-source/
RUN test -n "${OMEGA_VERSION}" \
 && rm -rf "${OMEGA_DIR}" \
 && mv /opt/omega-source "${OMEGA_DIR}" \
 && printf '%s\n' "${OMEGA_VERSION}" > "${OMEGA_DIR}/version" \
 && chmod 0444 "${OMEGA_DIR}/version" \
 && cp "${OMEGA_DIR}/run.metta" /PeTTa/run.metta \
 && install -o www-data -g www-data -m 0600 "${OMEGA_DIR}"/proxy/* /opt/nginx/ \
 && chmod +x "${OMEGA_DIR}/entrypoint.sh" "${OMEGA_DIR}/scripts/import_knowledge.sh" "${OMEGA_DIR}/scripts/omega"

# GoalChainer's locked environment, where the plugin's skills run as a child of the agent, with the
# semantic extra that reads text: sentence-transformers on CPU torch for the cross-encoder and
# typesafe-sdk for Jev. pymetta needs CPython 3.12 or newer and the image's python3 is 3.11, so uv
# brings its own CPython, kept where the agent's user, nobody, can run it, with bytecode compiled at
# install because nobody cannot write it later. uv's cache is a build cache mount, as uv's Docker
# guide keeps it, so a rebuild copies the locked wheels instead of downloading them again.
# pymetta comes from the native wheel directory the lock names relative to the checkout, mounted
# read-only at native-wheels/ for this step alone, so no wheel stays in the image; the plugin's
# installer later finds the environment with uv run --no-sync, which needs no directory. The committed
# verifier's place checks the directory against its MANIFEST before uv reads it, and its check, run
# by the environment's interpreter after the sync, requires every installed file of the wheel, the
# pool module and the bundled engine among them, to be the published bytes, and prints its identity.
# am[implements a-irp-image-semantic-1018@5d0f7c] am[rests-on c-irp-image-lacks-semantic-1018@e269c4]
# am[implements a-irp-image-native2-wheel-1018@ec11d2] am[rests-on c-rt-n2ic-find-links-relative-1018@e84f2c]
# am[rests-on c-irp-n2-uv-run-no-sync-1018@fdf5f5]
COPY --from=uv /uv /usr/local/bin/uv
COPY goalchainer/ /opt/goalchainer/
RUN --mount=type=cache,target=/opt/uv/cache \
    --mount=type=bind,from=native-wheels,target=/opt/goalchainer/native-wheels \
    cd /opt/goalchainer \
 && python3 -I scripts/native-wheels.py place \
 && UV_PYTHON_INSTALL_DIR=/opt/uv/python UV_CACHE_DIR=/opt/uv/cache UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    uv sync --frozen --extra semantic \
 && .venv/bin/python -I scripts/native-wheels.py check

# The reader's cross-encoder at the revision the gate pins, downloaded anonymously and verified file by
# file into a build cache, then copied to MODEL_CACHE and verified there. root owns it, so nobody
# reads it and nothing at run time changes it. A rebuild verifies the cached download instead of
# fetching it again.
# am[implements a-irp-image-semantic-1018@5d0f7c] am[rests-on c-integrate-image-reader-plan-agreed-1018@16672e]
ARG MODEL_CACHE=/opt/goalchainer/models
RUN --mount=type=cache,target=/var/cache/goalchainer-models,sharing=locked \
    GOALCHAINER_MODEL_CACHE=/var/cache/goalchainer-models /opt/goalchainer/.venv/bin/python -m goal_chainer.semantic_models provision \
 && mkdir -p "${MODEL_CACHE}" \
 && cp -a /var/cache/goalchainer-models/. "${MODEL_CACHE}/" \
 && GOALCHAINER_MODEL_CACHE="${MODEL_CACHE}" /opt/goalchainer/.venv/bin/python -m goal_chainer.semantic_models verify \
 && chmod -R a+rX,go-w "${MODEL_CACHE}"

# The plugin, installed as on any Omega checkout: the installer runs one skill in that environment,
# records its interpreter and its reader settings' defaults, and appends the plugin's record to
# config/plugins.yaml. The reader reads offline from an answer cache in the memory directory and
# asks Jev, through the gateway's /typesafe/ route, only once an operator sets goalchainerJevOffline
# to 0; Omega's configuration overrides each default. The memory directory then gets upstream's
# ownership and modes back.
# am[implements a-irp-gateway-route-1018@11ed50] am[rests-on c-irp-contract-1018@3ed0b0]
RUN OMEGACLAW_DIR="${OMEGA_DIR}" UV_PYTHON_INSTALL_DIR=/opt/uv/python /opt/goalchainer/scripts/setup-omegaclaw.sh \
      --model-cache "${MODEL_CACHE}" --jev-cache "${MEMORY_DIR}/goalchainer-jev" \
      --jev-offline 1 --jev-url http://localhost:8080/typesafe \
 && mkdir -p "${MEMORY_DIR}/chroma_db" \
 && chown -R 65534:65534 "${MEMORY_DIR}" \
 && find "${MEMORY_DIR}" -type f -exec chmod 0644 {} \; \
 && chmod 0444 "${MEMORY_DIR}/prompt.txt"

# Omega's gateway with one route more. nginx.sh renders the template NGINX_TEMPLATE names: here
# upstream's own with a /typesafe/ route, derived at build and checked against the nginx.sh the
# gateway starts from. A TYPESAFE_API_KEY given to docker run reaches only nginx, which starts before
# the entrypoint scrubs the agent's environment. TYPESAFE_UPSTREAM_URL names the service and ends in
# a slash, as upstream's own upstream URLs do. The route sends the key only to a server whose
# certificate verifies against TYPESAFE_TRUSTED_CERTIFICATE, by default the image's system CA bundle,
# the public roots typesafe-sdk itself trusts. nginx refuses to start without that file, so the build
# loads the bundle with OpenSSL, through python3's ssl, and stops if it holds no readable CA.
# am[implements a-irp-gateway-route-1018@11ed50] am[rests-on c-irp-upstream-url-needs-slash-1018@6bf3db]
# am[implements a-integrate-gateway-tls-verification-1018@ace531] am[rests-on c-irp-nginx-upstream-verify-1018@271329]
ENV NGINX_TEMPLATE=/opt/nginx/goalchainer.conf.template \
    TYPESAFE_UPSTREAM_URL=https://api.typesafe.ai/ \
    TYPESAFE_TRUSTED_CERTIFICATE=/etc/ssl/certs/ca-certificates.crt
RUN python3 -I -c 'import ssl, sys; assert ssl.create_default_context(cafile=sys.argv[1]).cert_store_stats()["x509_ca"]' \
      "${TYPESAFE_TRUSTED_CERTIFICATE}" \
 && python3 /opt/goalchainer/scripts/omega_gateway_template.py /opt/nginx "${NGINX_TEMPLATE}" \
 && chown www-data:www-data "${NGINX_TEMPLATE}" \
 && chmod 0600 "${NGINX_TEMPLATE}"

ARG GOALCHAINER_REVISION
LABEL org.opencontainers.image.title="Omega with the GoalChainer plugin" \
      org.opencontainers.image.revision="${GOALCHAINER_REVISION}" \
      org.opencontainers.image.version="${OMEGA_VERSION}"
