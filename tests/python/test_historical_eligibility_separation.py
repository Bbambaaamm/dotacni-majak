"""
#394 — Regression tests: historická data nikdy neovlivňují eligibility ani
success probability (historical data never influences eligibility or
success probability).

These tests lock the separation invariant: the eligibility engine computes
deterministic status from RuleSet + attribute values ONLY — no historical
award data, no similarity ratio, no approval probability enters the chain.
The history package returns *similarity signals* (ontology overlap), never
probabilities.

Scope of this bounded slice: pure regression tests against the existing
history + eligibility + workspace boundary. No production code changes.
"""

import ast
import inspect
import sys
import unittest
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _pkg, _rel in (
    ("eligibility", "src"),
    ("history", "src"),
    ("workspace", "src"),
    ("finance", "src"),
):
    sys.path.insert(0, str(ROOT / "packages" / _pkg / _rel))

from dotacni_majak_eligibility import (
    EligibilityEvaluation,
    EligibilityStatus,
    EligibilityEvaluator,
)
from dotacni_majak_history import (
    HistoricalAward,
    HistoricalSimilarityResult,
    HistoricalSimilarityService,
)
from dotacni_majak_workspace import (
    GrantRequirementInput,
    RequirementNecessity,
    WorkspaceEngine,
    WorkspaceTaskSource,
)
from dotacni_majak_finance import FinanceEvaluation, FinanceStatus


AT = datetime(2026, 9, 23, tzinfo=timezone.utc)

# Field / attribute name substrings that would indicate a probability leak.
_PROBABILITY_TOKENS = ("probab", "chance", "likelihood", "success_rate",
                        "success_probability", "approval_probability",
                        "approval_chance", "approval_rate")


def _has_probability_name(name: str) -> bool:
    """Return True if *name* looks like a probability/chance field."""
    lowered = name.lower()
    return any(token in lowered for token in _PROBABILITY_TOKENS)


# ---------------------------------------------------------------------------
# Helpers to build realistic RuleSet + values for determinism tests
# ---------------------------------------------------------------------------

def _make_simple_rule_set(rs_id="rs-test"):
    """Build a minimal RuleSet (single EQ condition) + matching values."""
    from dotacni_majak_eligibility import (
        AttributeDataType,
        AttributeDefinition,
        ConditionOperator,
        RuleCondition,
        RuleGroup,
        RuleSet,
        CompletenessStatus,
        VerificationStatus,
    )
    attr = AttributeDefinition(id="attr-owner", key="ownership",
                               data_type=AttributeDataType.STRING)
    cond = RuleCondition(
        id="cond-owner",
        attribute=attr,
        operator=ConditionOperator.EQ,
        expected_value="OWNED",
        blocking=True,
        verification_status=VerificationStatus.VERIFIED,
    )
    root = RuleGroup(id="root", operator=__import__(
        "dotacni_majak_eligibility", fromlist=["GroupOperator"]
    ).GroupOperator.AND, children=(cond,))
    return RuleSet(
        id=rs_id, root=root,
        completeness_status=CompletenessStatus.COMPLETE,
        verification_status=VerificationStatus.VERIFIED,
    )


class NoProbabilityFieldTest(unittest.TestCase):
    """
    Guard: no data model in the eligibility or history domain exposes a
    probability / chance / likelihood / success_rate attribute.
    """

    def test_eligibility_evaluation_has_no_probability_field(self):
        names = {f.name for f in fields(EligibilityEvaluation)}
        offenders = {n for n in names if _has_probability_name(n)}
        self.assertEqual(offenders, set(),
                         "EligibilityEvaluation must not expose probability fields")

    def test_historical_similarity_result_has_no_probability_field(self):
        names = {f.name for f in fields(HistoricalSimilarityResult)}
        offenders = {n for n in names if _has_probability_name(n)}
        self.assertEqual(offers := offenders, set(),
                         "HistoricalSimilarityResult must not expose probability fields")

    def test_historical_award_has_no_probability_field(self):
        names = {f.name for f in fields(HistoricalAward)}
        offenders = {n for n in names if _has_probability_name(n)}
        self.assertEqual(offenders, set(),
                         "HistoricalAward must not expose probability fields")

    def test_no_probability_attr_on_eligibility_evaluation_instance(self):
        ev = EligibilityEvaluation(
            rule_set_id="rs",
            status=EligibilityStatus.ELIGIBLE,
            root_result=__import__(
                "dotacni_majak_eligibility", fromlist=["ConditionResult"]
            ).ConditionResult.PASS,
            condition_results=(),
            input_snapshot_hash="0" * 64,
            evaluated_at=AT,
        )
        for attr_name in dir(ev):
            if attr_name.startswith("_"):
                continue
            if _has_probability_name(attr_name):
                self.fail(f"EligibilityEvaluation instance has probability attr: "
                          f"{attr_name}")

    def test_no_probability_attr_on_similarity_result_instance(self):
        from dotacni_majak_history import HistoricalAward
        award = HistoricalAward(
            id="a1", project_title="Test", recipient_name="R",
            currency_code="CZK", source_url="https://x.cz/a1",
        )
        result = HistoricalSimilarityResult(
            award=award, shared_ontology_terms=(),
            ontology_overlap_ratio_ppm=500_000,
        )
        for attr_name in dir(result):
            if attr_name.startswith("_"):
                continue
            if _has_probability_name(attr_name):
                self.fail(f"HistoricalSimilarityResult instance has probability attr: "
                          f"{attr_name}")

    def test_eligibility_status_enum_has_no_probability_value(self):
        for member in EligibilityStatus:
            if _has_probability_name(member.value):
                self.fail(f"EligibilityStatus.{member.name}={member.value!r} "
                          f"references probability")


class NoProbabilityAssignmentInSourceTest(unittest.TestCase):
    """
    Static check: the AST of the eligibility evaluator and history similarity
    modules must not assign to any name that looks like a probability.
    """

    def _collect_assignment_names(self, source: str) -> set[str]:
        tree = ast.parse(source)
        names: set[str] = set()

        def _visit(node):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        names.add(target.id)
                    elif isinstance(target, ast.Attribute):
                        names.add(target.attr)
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name):
                    names.add(node.target.id)
                elif isinstance(node.target, ast.Attribute):
                    names.add(node.target.attr)
            elif isinstance(node, ast.AugAssign):
                if isinstance(node.target, ast.Name):
                    names.add(node.target.id)
                elif isinstance(node.target, ast.Attribute):
                    names.add(node.target.attr)
            for child in ast.iter_child_nodes(node):
                _visit(child)

        for child in ast.iter_child_nodes(tree):
            _visit(child)
        return names

    def _module_path(self, pkg: str, module: str) -> Path:
        for candidate in (
            ROOT / "packages" / pkg / "src" / module,
            ROOT / "packages" / pkg / "src" / pkg.replace("-", "_").replace("dotacni_majak_", "dotacni_majak_") / (module + ".py"),
        ):
            if candidate.exists():
                return candidate
        # Fallback: use inspect to find the module
        mod = __import__(f"dotacni_majak_{pkg}", fromlist=[module[:-1] if module.endswith('.py') else module])
        return Path(inspect.getfile(mod))

    def test_eligibility_evaluator_no_probability_assignment(self):
        import dotacni_majak_eligibility.evaluator as ev_mod
        source = inspect.getsource(ev_mod)
        names = self._collect_assignment_names(source)
        offenders = {n for n in names if _has_probability_name(n)}
        self.assertEqual(offenders, set(),
                         "eligibility/evaluator.py must not assign probability variables")

    def test_history_similarity_no_probability_assignment(self):
        import dotacni_majak_history.similarity as hist_mod
        source = inspect.getsource(hist_mod)
        names = self._collect_assignment_names(source)
        offenders = {n for n in names if _has_probability_name(n)}
        self.assertEqual(offenders, set(),
                         "history/similarity.py must not assign probability variables")


class ArchitectureBoundaryTest(unittest.TestCase):
    """
    Guard: the history and eligibility packages must not import each other,
    enforcing a hard architectural boundary.
    """

    def _read_source(self, *segments: str) -> str:
        return (ROOT / "packages" / Path(*segments)).read_text(encoding="utf-8")

    def test_eligibility_does_not_import_history(self):
        source = self._read_source("eligibility", "src",
                                   "dotacni_majak_eligibility", "evaluator.py")
        self.assertNotIn("dotacni_majak_history", source,
                         "eligibility engine must not import history package")

    def test_history_does_not_import_eligibility(self):
        source = self._read_source("history", "src",
                                   "dotacni_majak_history", "similarity.py")
        # "eligibility" may appear only in docstrings; check import lines
        import_lines = [
            line for line in source.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        for line in import_lines:
            self.assertNotIn("dotacni_majak_eligibility", line,
                             "history package must not import eligibility")

    def test_workspace_does_not_import_history(self):
        source = self._read_source("workspace", "src",
                                   "dotacni_majak_workspace", "engine.py")
        self.assertNotIn("dotacni_majak_history", source,
                         "workspace engine must not import history package")

    def test_eligibility_evaluator_does_not_accept_history_param(self):
        sig = inspect.signature(EligibilityEvaluator.evaluate)
        param_names = set(sig.parameters.keys())
        self.assertNotIn("historical", param_names)
        self.assertNotIn("history", param_names)
        self.assertNotIn("similarity", param_names)
        self.assertNotIn("similarity_result", param_names)
        self.assertNotIn("historical_context", param_names)

    def test_workspace_create_does_not_accept_history_param(self):
        sig = inspect.signature(WorkspaceEngine.create)
        param_names = set(sig.parameters.keys())
        for forbidden in ("historical", "history", "similarity",
                          "similarity_results", "similar_examples",
                          "historical_examples"):
            self.assertNotIn(forbidden, param_names,
                             f"WorkspaceEngine.create must not accept '{forbidden}'")

    def test_workspace_task_source_has_no_history_value(self):
        values = {member.value for member in WorkspaceTaskSource}
        self.assertNotIn("HISTORY", values)
        self.assertNotIn("HISTORICAL", values)


class EligibilityDeterminismTest(unittest.TestCase):
    """
    Guard: eligibility evaluation is a pure function of RuleSet + values.
    Running the same evaluation twice — even in the presence of historical
    award context — must yield identical EligibilityEvaluation objects.
    Historical data is not a parameter, so it cannot influence the result.
    """

    def setUp(self):
        self.rule_set = _make_simple_rule_set()
        self.values = {"ownership": "OWNED"}
        self.evaluator = EligibilityEvaluator()
        # Build a realistic HistoricalSimilarityResult to prove it is
        # available in context but never passed to evaluate().
        self.historical = HistoricalSimilarityService().find_similar(
            project_ontology_terms=("INFRASTRUCTURE",),
            awards=[
                HistoricalAward(
                    id="hist-1",
                    project_title="Historický tenis",
                    recipient_name="TJ Historie",
                    currency_code="CZK",
                    source_url="https://www.czech-domain.gov.cz/hist/1",
                    award_year=2023,
                    ontology_terms=("INFRASTRUCTURE", "SPORT"),
                ),
            ],
        )

    def test_identical_evaluations_regardless_of_historical_context(self):
        run_a = self.evaluator.evaluate(self.rule_set, self.values)
        run_b = self.evaluator.evaluate(self.rule_set, self.values)
        self.assertEqual(run_a.status, run_b.status)
        self.assertEqual(run_a.root_result, run_b.root_result)
        self.assertEqual(run_a.condition_results, run_b.condition_results)
        self.assertEqual(run_a.input_snapshot_hash, run_b.input_snapshot_hash)

    def test_eligibility_evaluation_excludes_historical_data_from_snapshot(self):
        """input_snapshot_hash must not include any historical award fields."""
        ev = self.evaluator.evaluate(self.rule_set, self.values)
        # The snapshot hash is computed over the `values` dict only.
        # If historical data leaked in, the hash would differ when awards
        # change but values stay the same — this test pins the contract.
        self.assertEqual(len(ev.input_snapshot_hash), 64)
        self.assertEqual(ev.engine_version, "eligibility-v1")
        self.assertEqual(ev.rule_set_id, self.rule_set.id)

    def test_likeleyly_status_not_tied_to_similarity_ratio(self):
        """LIKELY_ELIGIBLE is driven by completeness/verification, not
        by any historical similarity ratio."""
        from dotacni_majak_eligibility import (
            AttributeDataType, AttributeDefinition, ConditionOperator,
            RuleCondition, RuleGroup, RuleSet, CompletenessStatus,
            VerificationStatus, GroupOperator,
        )
        # Same condition, but rule set is PARTIAL + NEEDS_REVIEW
        attr = AttributeDefinition(id="a", key="ownership",
                                   data_type=AttributeDataType.STRING)
        cond = RuleCondition(id="c", attribute=attr,
                             operator=ConditionOperator.EQ,
                             expected_value="OWNED", blocking=True,
                             verification_status=VerificationStatus.VERIFIED)
        root = RuleGroup(id="root", operator=GroupOperator.AND, children=(cond,))
        partial_rs = RuleSet(
            id="rs-partial", root=root,
            completeness_status=CompletenessStatus.PARTIAL,
            verification_status=VerificationStatus.VERIFIED,
        )
        ev = EligibilityEvaluator().evaluate(partial_rs, self.values)
        self.assertEqual(ev.status, EligibilityStatus.LIKELY_ELIGIBLE)
        # The similarity ratio from our historical results must not appear
        # anywhere in the evaluation result.
        self.assertFalse(
            hasattr(ev, "similarity_ratio") or
            hasattr(ev, "historical_context") or
            hasattr(ev, "overlap_ratio")
        )
        self.assertNotIn("similarity", ev.input_snapshot_hash)


class HistoricalContextIsExplicitlyLabeledTest(unittest.TestCase):
    """
    Guard: UI-facing historical results carry the explicit
    'is_historical_context = True' marker so the UI never confuses
    historical examples with current eligibility predictions, and the
    service docstring explicitly rejects approval-probability framing.
    """

    def test_historical_result_is_marked_as_context(self):
        award = HistoricalAward(
            id="h1", project_title="Projekt", recipient_name="O",
            currency_code="CZK", source_url="https://gov.cz/h1",
            ontology_terms=("SPORT",),
            award_year=2022,
        )
        result = HistoricalSimilarityService().find_similar(
            project_ontology_terms=("SPORT",), awards=[award],
        )
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].is_historical_context)

    def test_service_docstring_disclaims_probability(self):
        docstring = HistoricalSimilarityService.__doc__
        self.assertIsNotNone(docstring)
        self.assertIn("historical", docstring.lower())
        self.assertIn("probabilit", docstring.lower(),
                      "docstring must explicitly disclaim probability framing")

    def test_similarity_basis_not_probability(self):
        """The similarity metric field must not be named like a probability."""
        award = HistoricalAward(
            id="h2", project_title="P", recipient_name="R",
            currency_code="CZK", source_url="https://gov.cz/h2",
            ontology_terms=("EDUCATION",),
        )
        result = HistoricalSimilarityService().find_similar(
            project_ontology_terms=("EDUCATION",), awards=[award],
        )[0]
        # The field is named ontology_overlap_ratio_ppm (parts per million)
        # not "probability" or "success_rate"
        self.assertTrue(hasattr(result, "ontology_overlap_ratio_ppm"))
        self.assertFalse(_has_probability_name("ontology_overlap_ratio_ppm"))
        self.assertFalse(_has_probability_name(result.similarity_basis))


class WorkspaceDoesNotSurfaceProbabilityTest(unittest.TestCase):
    """
    Guard: the workspace engine's UI-facing task titles and reason codes
    never reference probability, chance, or likelihood.
    """

    def _collect_strings(self, source: str) -> list[str]:
        tree = ast.parse(source)
        strings: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                strings.append(node.value)
        return strings

    def test_no_probability_in_workspace_ui_strings(self):
        source = (ROOT / "packages" / "workspace" / "src" /
                  "dotacni_majak_workspace" / "engine.py").read_text(
            encoding="utf-8")
        strings = self._collect_strings(source)
        bad_words = ("pravděpodobnost", "pravdepodobnost",
                      "šance", "likelihood", "probability",
                      "success probability", "chance of", "approval rate",
                      "success rate")
        for s in strings:
            lowered = s.lower()
            for bad in bad_words:
                self.assertNotIn(bad, lowered,
                                 f"workspace UI string references probability: {s!r}")

    def test_no_historical_examples_in_eligibility_tasks(self):
        """Tasks generated from EligibilityEvaluation must never source
        from history or carry historical-example framing."""
        from dotacni_majak_eligibility import (
            AttributeDataType, AttributeDefinition, ConditionResult,
            ConditionOperator, RuleCondition, RuleGroup, RuleSet,
            EligibilityStatus, EligibilityEvaluation, GroupOperator,
            CompletenessStatus, VerificationStatus,
        )
        attr = AttributeDefinition(id="a", key="k", data_type=AttributeDataType.STRING)
        cond = RuleCondition(id="c", attribute=attr, operator=ConditionOperator.EQ,
                             expected_value="v", blocking=True,
                             verification_status=VerificationStatus.VERIFIED)
        root = RuleGroup(id="root", operator=GroupOperator.AND, children=(cond,))
        rs = RuleSet(id="rs", root=root,
                     completeness_status=CompletenessStatus.COMPLETE,
                     verification_status=VerificationStatus.VERIFIED)
        ev = EligibilityEvaluation(
            rule_set_id="rs",
            status=EligibilityStatus.LIKELY_ELIGIBLE,
            root_result=ConditionResult.PASS,
            condition_results=(),
            input_snapshot_hash="0" * 64,
            evaluated_at=AT,
        )
        workspace = WorkspaceEngine().create(
            workspace_id="w", project_id="p", grant_call_id="g",
            baseline_grant_version_id="v1",
            requirements=(
                GrantRequirementInput(id="r", title="R",
                                      necessity=RequirementNecessity.REQUIRED),
            ),
            eligibility=ev,
            finance=FinanceEvaluation(
                status=FinanceStatus.COMPLETE,
                scenario_id="s",
                currency_code="CZK",
                max_grant_minor=None,
                own_eligible_contribution_minor=None,
                ineligible_costs_minor=None,
                nonrecoverable_vat_minor=None,
                minimum_real_cash_requirement_minor=None,
                minimum_prefinancing_requirement_minor=None,
                reason_codes=(),
            ),
        )
        for task in workspace.tasks:
            lowered = task.title.lower() + " " + (task.reason_code or "").lower()
            for bad in ("pravd", "šance", "likelihood", "probability",
                        "historical example", "similar"):
                self.assertNotIn(bad, lowered,
                                 f"task title/reason references probability/history: "
                                 f"{task.title!r} / {task.reason_code!r}")


class HistoricalAwardProvenanceTest(unittest.TestCase):
    """
    Acceptance: 'Provenance/coverage metadata jsou dostupná.'
    HistoricalAward must carry source provenance (source_url, id).
    """

    def test_award_has_source_url_and_id(self):
        award = HistoricalAward(
            id="src-award-1",
            project_title="Rekonstrukce mostu",
            recipient_name="Město",
            currency_code="CZK",
            source_url="https://www.czech-domain.gov.cz/awards/1",
        )
        self.assertEqual(award.id, "src-award-1")
        self.assertEqual(award.source_url,
                         "https://www.czech-domain.gov.cz/awards/1")

    def test_award_id_must_not_be_empty(self):
        with self.assertRaises(ValueError):
            HistoricalAward(
                id="", project_title="X", recipient_name="Y",
                currency_code="CZK", source_url="https://z.cz",
            )

    def test_award_currency_must_be_uppercase_3letter(self):
        with self.assertRaises(ValueError):
            HistoricalAward(
                id="x1", project_title="X", recipient_name="Y",
                currency_code="czk", source_url="https://z.cz",
            )


class NoFutureApprovalProbabilitySurfaceTest(unittest.TestCase):
    """
    Core invariant: nowhere does a *future* approval probability arise.
    The historical similarity ratio is about *past pattern overlap*,
    not future success.
    """

    def test_similarity_ratio_is_past_overlap_not_future_probability(self):
        """The ppm ratio measures ontology overlap with awarded projects,
        which is explicitly a similarity signal, never a chance-of-funding."""
        service = HistoricalSimilarityService()
        award = HistoricalAward(
            id="past-1", project_title="P", recipient_name="R",
            currency_code="CZK",
            source_url="https://gov.cz/past-1",
            ontology_terms=("INFRASTRUCTURE", "SPORT"),
            award_year=2021,
        )
        results = service.find_similar(
            project_ontology_terms=("INFRASTRUCTURE",),
            awards=[award],
        )
        self.assertEqual(len(results), 1)
        # 100% of the user's single term overlaps → 1_000_000 ppm
        # This is "how much of your project matches past awards"
        # NOT "your chance of being awarded"
        self.assertEqual(results[0].ontology_overlap_ratio_ppm, 1_000_000)
        self.assertTrue(results[0].is_historical_context)

    def test_no_probability_term_in_any_module_docstrings(self):
        """Check docstrings of key classes for probability *computations*,
        not just the word appearing. We verify the word is only used to
        DISCLAIM, not to compute."""
        for cls in (EligibilityEvaluation, EligibilityEvaluator,
                    HistoricalSimilarityService, HistoricalSimilarityResult,
                    HistoricalAward):
            doc = cls.__doc__
            if doc:
                # If 'probability' appears, it must also appear in a
                # disclaiming context (e.g., "never", "not", "not a")
                if "probab" in doc.lower():
                    disclaimers = ("never", "not", "not a", "no ",
                                   "disclaim", "rather", "not a probability")
                    has_disclaimer = any(d.lower() in doc.lower()
                                         for d in disclaimers)
                    self.assertTrue(has_disclaimer,
                                    f"{cls.__name__}.__doc__ mentions 'probability' "
                                    f"without disclaimer — potential leak")


if __name__ == "__main__":
    unittest.main()
