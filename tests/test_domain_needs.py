"""Purpose: verify goal_chainer.domains.needs reads a domain's gc-need and gc-need-expectation forms
into its records, refuses a form of the wrong shape naming the file and the form, and that the
domain loader digests every need form and reports every relational fault of the section at once."""

from __future__ import annotations

import pytest

from goal_chainer.domains.forms import parsed_forms
from goal_chainer.domains.loader import read_domain
from goal_chainer.domains.model import DomainError
from goal_chainer.domains.needs import Need, NeedExpectation, NeedSection, read_section
from goal_chainer.runtime.budget import RunBudget

CORE = """
(gc-domain "Needs section fixture")
(gc-policy-version needs-fixture-v1)
(gc-authority advisory 1 "A recommendation for the host.")
(gc-authority preauthorized 2 "Applied inside a declared envelope.")
(gc-estimator-ceiling model-proposed advisory)
(gc-estimator-ceiling receipt-calibrated preauthorized)
(gc-estimator-ceiling measured preauthorized)
(gc-estimator-ceiling deterministic preauthorized)
(gc-estimator-ceiling human-asserted preauthorized)
(gc-action empathize "Empathize" "Reflect the feeling back." (authority preauthorized))
(gc-action guide_breath "Guide breath" "Lead a breathing practice." (authority preauthorized))
(gc-goal nurturing agent individual 0.9 "The student's suffering is eased." (priority-source human:designer))
(gc-goal competence agent individual 0.7 "The guidance is effective." (priority-source human:designer))
(gc-signal session_open "a session is open")
(normally rCand (signal session_open) (candidate ?a))
(normally rPermit (candidate ?a) (may (do ?a)))
"""

SECTION = """
(gc-need nurture-level nurturing (scale 0 1) (band 0.6 0.9) (drive 2) (need-source human:designer))
(gc-need skill-level competence (scale -1 1) (band 0 1) (drive 1.5) (need-source human:designer))
(gc-need-expectation empathize nurture-level 0.3 human-asserted (expectation-source human:designer))
(gc-need-expectation guide_breath skill-level -0.25 measured (expectation-source pilot:2026))
"""


# am[verifies a-v2m-need-forms-1019@6ee59c]
def _budget() -> RunBudget:
    return RunBudget(inference_budget=None, timeout_seconds=300)


# am[verifies a-v2m-need-forms-1019@6ee59c]
def _read(text: str) -> NeedSection:
    return read_section(parsed_forms(text, budget=None), "domains/data/example.metta")


# am[verifies a-v2m-need-forms-1019@6ee59c]
def test_a_section_reads_into_its_records_in_declared_order() -> None:
    section = _read(SECTION)

    assert section.needs == (
        Need("nurture-level", "nurturing", (0.0, 1.0), (0.6, 0.9), 2.0, "human:designer"),
        Need("skill-level", "competence", (-1.0, 1.0), (0.0, 1.0), 1.5, "human:designer"),
    )
    assert section.expectations == (
        NeedExpectation("empathize", "nurture-level", 0.3, "human-asserted", "human:designer"),
        NeedExpectation("guide_breath", "skill-level", -0.25, "measured", "pilot:2026"),
    )


# A setpoint is a band of zero width and a whole-scale band never regulates anything; both are
# shapes a domain may declare.
# am[verifies a-v2m-need-forms-1019@6ee59c]
@pytest.mark.parametrize("band", ["(band 0.5 0.5)", "(band 0 1)"])
def test_a_setpoint_and_a_whole_scale_band_are_declarable(band: str) -> None:
    (need,) = _read(f"(gc-need n g (scale 0 1) {band} (drive 1) (need-source s))").needs
    assert need.band[0] <= need.band[1]


# am[verifies a-v2m-need-forms-1019@6ee59c]
@pytest.mark.parametrize(
    "form",
    [
        "(gc-need n g (scale 1 0) (band 0.2 0.4) (drive 1) (need-source s))",
        "(gc-need n g (scale 0 0) (band 0 0) (drive 1) (need-source s))",
        "(gc-need n g (scale 0 1) (band 0.4 0.2) (drive 1) (need-source s))",
        "(gc-need n g (scale 0 1) (band -0.1 0.4) (drive 1) (need-source s))",
        "(gc-need n g (scale 0 1) (band 0.2 1.1) (drive 1) (need-source s))",
        "(gc-need n g (scale 0 1) (band 0.2 0.4) (drive 0) (need-source s))",
        "(gc-need n g (scale 0 1) (band 0.2 0.4) (drive -2) (need-source s))",
        "(gc-need n g (scale 0 1) (band 0.2 0.4) (drive 0.5) (need-source s))",
        "(gc-need n g (scale -1e308 1e308) (band -1 1) (drive 1) (need-source s))",
        "(gc-need n g (scale 0 1) (band 0.2 0.4) (drive inf) (need-source s))",
        "(gc-need n g (scale 0 nan) (band 0.2 0.4) (drive 1) (need-source s))",
        "(gc-need n g (scale 0 1) (band 0.2 0.4) (drive 1))",
        "(gc-need n g (scale 0 1 2) (band 0.2 0.4) (drive 1) (need-source s))",
        "(gc-need n g (scale 0 1) (band 0.2 0.4) (drive 1) (priority-source s))",
        '(gc-need "n" g (scale 0 1) (band 0.2 0.4) (drive 1) (need-source s))',
        "(gc-need n g (scale 0 True) (band 0.2 0.4) (drive 1) (need-source s))",
        "(gc-need-expectation a n big measured (expectation-source s))",
        "(gc-need-expectation a n 0.1 measured)",
        '(gc-need-expectation a n 0.1 "measured" (expectation-source s))',
        "(gc-need-expectation a n 0.1 measured (need-source s))",
    ],
)
def test_a_form_of_the_wrong_shape_is_refused_naming_the_file_and_the_form(form: str) -> None:
    with pytest.raises(DomainError, match=r"domains/data/example\.metta: \(gc-need.* should be \(gc-need"):
        _read(form)


# am[verifies a-v2m-need-forms-1019@6ee59c]
def test_a_domain_without_need_forms_has_no_motivation() -> None:
    domain = read_domain(CORE, "core.metta", budget=_budget())

    assert domain.motivation is None
    assert domain.needs == () and domain.need_expectations == () and domain.need_ids == ()


# Every need form is review-relevant, so changing a band or adding a form changes the digest the
# review fingerprints, and the goal priorities stay as declared.
# am[verifies a-v2m-need-forms-1019@6ee59c] am[verifies a-rel-nd-review-digest-scope-1018@96d474]
def test_the_digest_covers_every_need_form_and_the_goals_keep_their_weights() -> None:
    plain = read_domain(CORE, "d.metta", budget=_budget())
    regulated = read_domain(CORE + SECTION, "d.metta", budget=_budget())
    moved = read_domain(CORE + SECTION.replace("(band 0.6 0.9)", "(band 0.6 0.8)"), "d.metta", budget=_budget())

    assert len({plain.digest, regulated.digest, moved.digest}) == 3
    assert regulated.need_ids == ("nurture-level", "skill-level")
    assert regulated.need("skill-level").drive == 1.5
    assert [goal.weight for goal in regulated.goals] == [goal.weight for goal in plain.goals] == [0.9, 0.7]
    with pytest.raises(DomainError, match="no such need in d.metta: thirst"):
        regulated.need("thirst")


# One DomainError lists every relational fault: a need id declared twice, a goal no gc-goal
# declares, a goal two needs regulate, an expectation of an undeclared action or need, a second
# expectation of one action and need, an unknown estimator class and a change wider than the scale.
# am[verifies a-v2m-need-forms-1019@6ee59c]
def test_every_relational_fault_of_the_section_is_reported_at_once() -> None:
    faulty = CORE + """
(gc-need nurture-level nurturing (scale 0 1) (band 0.6 0.9) (drive 2) (need-source s))
(gc-need nurture-level competence (scale 0 1) (band 0.6 0.9) (drive 2) (need-source s))
(gc-need thirst hydration (scale 0 1) (band 0.6 0.9) (drive 2) (need-source s))
(gc-need warmth nurturing (scale 0 1) (band 0.6 0.9) (drive 2) (need-source s))
(gc-need-expectation hug nurture-level 0.1 measured (expectation-source s))
(gc-need-expectation empathize calm 0.1 measured (expectation-source s))
(gc-need-expectation empathize warmth 0.1 measured (expectation-source s))
(gc-need-expectation empathize warmth 0.2 measured (expectation-source s))
(gc-need-expectation guide_breath warmth 0.1 guessed (expectation-source s))
(gc-need-expectation guide_breath thirst -1.5 measured (expectation-source s))
"""
    with pytest.raises(DomainError) as refused:
        read_domain(faulty, "faulty.metta", budget=_budget())

    faults = refused.value.faults
    assert faults == (
        '(Need "nurture-level" "nurturing") is not the only gc-need of its id',
        '(Need "nurture-level" "nurturing") regulates a goal another gc-need regulates too, '
        "which would count the goal's priority twice",
        '(Need "nurture-level" "competence") is not the only gc-need of its id',
        '(Need "thirst" "hydration") regulates a goal no gc-goal declares',
        '(Need "warmth" "nurturing") regulates a goal another gc-need regulates too, '
        "which would count the goal's priority twice",
        '(Expectation "hug" "nurture-level" 0.1 "measured") declares a change for an action no gc-action declares',
        '(Expectation "empathize" "calm" 0.1 "measured") declares a change of a need no gc-need declares',
        '(Expectation "empathize" "warmth" 0.1 "measured") is not the only gc-need-expectation of its action and need',
        '(Expectation "empathize" "warmth" 0.2 "measured") is not the only gc-need-expectation of its action and need',
        '(Expectation "guide_breath" "warmth" 0.1 "guessed") names an estimator class the shared vocabulary does not hold',
        '(Expectation "guide_breath" "thirst" -1.5 "measured") declares a change larger than its need\'s whole scale',
    )


# A record built in code is held to the shape the reader checks, so no ill-formed need reaches a
# consumer by another route.
# am[verifies a-v2m-need-forms-1019@6ee59c]
@pytest.mark.parametrize(
    "scale, band, drive",
    [
        ((1.0, 0.0), (0.2, 0.4), 1.0),
        ((0.0, 1.0), (0.4, 0.2), 1.0),
        ((0.0, 1.0), (0.2, 0.4), 0.0),
        ((0.0, 1.0), (0.2, 0.4), 0.99),
        ((-1e308, 1e308), (-1.0, 1.0), 1.0),
        ((-9e307, 9e307), (-1.0, 1.0), 1.0),
        ((0.0, float("inf")), (0.2, 0.4), 1.0),
        ((0.0, 1.0), (0.2, float("nan")), 1.0),
        ((False, 1.0), (0.2, 0.4), 1.0),
        ((0.0, 10**400), (0.2, 0.4), 1.0),
    ],
)
def test_an_ill_formed_need_cannot_be_built(scale: tuple, band: tuple, drive: float) -> None:
    with pytest.raises(ValueError, match="need n:"):
        Need("n", "g", scale, band, drive, "s")


# am[verifies a-v2m-need-forms-1019@6ee59c]
@pytest.mark.parametrize("change", [float("nan"), float("-inf"), True, "0.1"])
def test_an_expectation_without_a_finite_change_cannot_be_built(change: object) -> None:
    with pytest.raises(ValueError, match="must be a finite number"):
        NeedExpectation("a", "n", change, "measured", "s")  # type: ignore[arg-type]


# Equal numbers keep one spelling, so equal needs serialise and fingerprint alike.
# am[verifies a-v2m-need-forms-1019@6ee59c]
def test_a_negative_zero_is_kept_as_zero() -> None:
    need = Need("n", "g", (-0.0, 1), (-0.0, 0.5), 2, "s")
    assert [str(value) for value in (*need.scale, *need.band, need.drive)] == ["0.0", "1.0", "0.0", "0.5", "2.0"]
    assert str(NeedExpectation("a", "n", -0.0, "measured", "s").change) == "0.0"
