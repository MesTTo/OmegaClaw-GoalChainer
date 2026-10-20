"""Purpose: resolve the checkouts GoalChainer's native stack runs on. Every native dependency is a
submodule under external/, so a clone resolves the pinned trees by default; an explicit path, or the
dependency's environment variable, names another. A checkout that is missing or lacks its marker
file is a DependencyUnavailableError naming the path, the source it came from and how to provide
it, never a fallback to some other tree."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ..errors import DependencyUnavailableError


REPO_ROOT = Path(__file__).resolve().parents[3]


# am[implements a-rt-vendored-defaults-1016@182749]
@dataclass(frozen=True, slots=True)
class Checkout:
    """One native dependency: the external/<directory> submodule, the variables that may name
    another checkout in precedence order, and a file only a usable checkout has."""

    label: str
    directory: str
    variables: tuple[str, ...]
    marker: str

# Upstream Omega, formerly OmegaClaw-Core, kept in external/OmegaClaw-Core; lib_omega.metta is what its
# run.metta imports.
# am[implements a-oc-plugin-pin-1018@391e69] am[rests-on c-oc-upstream-moved-1018@5d3f58]
OMEGACLAW_CORE = Checkout(
    "Omega", "OmegaClaw-Core", ("GOALCHAINER_OMEGACLAW_DIR",), "lib_omega.metta"
)

PETTACHAINER = Checkout(
    "PeTTaChainer",
    "PeTTaChainer",
    ("GOALCHAINER_PETTACHAINER_DIR",),
    "pettachainer/metta/petta_chainer.metta",
)


# am[implements a-rt-vendored-defaults-1016@182749]
def checkout_source(
    checkout: Checkout,
    explicit: str | os.PathLike[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    repo_root: str | os.PathLike[str] | None = None,
) -> tuple[Path, str]:
    """The directory a checkout comes from and what named it: "explicit", the variable, or
    "vendored" for external/<directory> under repo_root."""

    if explicit is not None:
        return Path(explicit).expanduser().resolve(), "explicit"
    values = os.environ if env is None else env
    for variable in checkout.variables:
        if values.get(variable):
            return Path(values[variable]).expanduser().resolve(), variable
    root = REPO_ROOT if repo_root is None else Path(repo_root)
    return (root / "external" / checkout.directory).resolve(), "vendored"


# am[implements a-rt-vendored-defaults-1016@182749]
def checkout_dir(
    checkout: Checkout,
    explicit: str | os.PathLike[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    repo_root: str | os.PathLike[str] | None = None,
) -> Path:
    """The checkout's directory, refused unless it holds the checkout's marker file."""

    path, source = checkout_source(checkout, explicit, env=env, repo_root=repo_root)
    if not (path / checkout.marker).is_file():
        remedy = (
            f"run `git submodule update --init external/{checkout.directory}`"
            if source == "vendored"
            else f"point {source} at a {checkout.label} checkout"
        )
        raise DependencyUnavailableError(
            f"{checkout.label} is unavailable at {path} ({source}): it has no {checkout.marker}; "
            f"{remedy}, or set {checkout.variables[0]}.",
            details={
                "dependency": checkout.label,
                "path": str(path),
                "source": source,
                "marker": checkout.marker,
            },
        )
    return path
