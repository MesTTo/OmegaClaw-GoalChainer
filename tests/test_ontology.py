from goal_chainer.ontology import load_colore_context


def test_load_colore_context_counts_and_selects_axioms(tmp_path):
    fixture = tmp_path / "data-colore.metta"
    fixture.write_text(
        "\n".join(
            [
                '(colore module timepoints/lp_ordering "http://example/lp_ordering.clif")',
                "(colore axiom timepoints/lp_ordering a1 horn (forall ($x $y $z) (if (and (before $x $y) (before $y $z)) (before $x $z))))",
                "(colore pred timepoints/lp_ordering before 2)",
                '(colore module kinship/definitions/hasGrandchild "http://example/hasGrandchild.clif")',
                "(colore axiom kinship/definitions/hasGrandchild HGC-1 definition (forall ($x $z) (iff (hasGrandchild $x $z) (exists ($y) (and (hasChild $x $y) (hasChild $y $z))))))",
                '(colore gloss kinship/definitions/hasGrandchild HGC-1 "A person has a grandchild if their child has a child.")',
                "(colore pred kinship/definitions/hasGrandchild hasChild 2)",
                "(colore pred kinship/definitions/hasGrandchild hasGrandchild 2)",
            ]
        )
    )

    context = load_colore_context(fixture)

    assert context.source_available
    assert context.module_count == 2
    assert context.axiom_count == 2
    assert context.predicate_count == 3
    assert context.axiom_kinds == {"horn": 1, "definition": 1}
    assert [axiom.source for axiom in context.selected_axioms] == [
        "timepoints/lp_ordering/a1",
        "kinship/definitions/hasGrandchild/HGC-1",
    ]
    assert context.projection_rules[0]["available"] is True
    assert context.projection_rules[1]["gloss"] == "A person has a grandchild if their child has a child."


def test_missing_colore_context_still_returns_projection_contract(tmp_path):
    context = load_colore_context(tmp_path / "missing.metta")

    assert context.source_available is False
    assert context.module_count == 0
    assert context.projection_rules[0]["available"] is False
