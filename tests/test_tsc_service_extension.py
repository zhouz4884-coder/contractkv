import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from scripts.build_tsc_service_trace import FAMILIES, build_arrivals, select_sessions
from scripts.build_tsc_service_quality_trace import build as build_quality_templates
from scripts.build_tsc_residency_arrivals import build as build_residency_arrivals
from scripts.build_tsc_service_locality_traces import stable_segments, variant, variant_template_count
from scripts.tsc_open_loop_service import registration_scope, request_cache_salt, slope
from scripts.tsc_multi_tenant_live import jain, summarize as summarize_tenants, tenant_specs
from scripts.tsc_service_lifecycle_live import baseline_scope, mutate
from scripts.tsc_verification_economics_live import BOUNDARY_POINTS, contour
from scripts.summarize_tsc_service_extension import certificate_outcome_consistent, locality_capacity
from scripts.validate_tsc_locality_pilot import evaluate as evaluate_locality_pilot


class TscServiceExtensionTests(unittest.TestCase):
    def _pool(self, per_family=3):
        rows = []
        specs = [
            ("RULER", "niah_single_1"),
            ("LongBench", "hotpotqa"),
            ("LongBench", "narrativeqa"),
            ("LongBench", "qasper"),
            ("RepoBench", "python_v1.1"),
        ]
        for dataset, task in specs:
            for index in range(per_family):
                rows.append({
                    "dataset": dataset,
                    "task": task,
                    "sample_id": str(index),
                    "metadata": {
                        "phase14_partition": "live_serving",
                        "source_group_id": f"{dataset}:{task}:{index}",
                    },
                    "segments": [],
                })
        return rows

    def test_trace_has_unique_groups_and_exact_future_count(self):
        sessions = select_sessions(self._pool(), per_family=3, seed=27001)
        self.assertEqual(len(sessions), 15)
        self.assertEqual({row["tsc_family"] for row in sessions}, set(FAMILIES))
        self.assertEqual(len({row["metadata"]["source_group_id"] for row in sessions}), 15)
        arrivals = build_arrivals(sessions, turns=10, seed=27002)
        self.assertEqual(len(arrivals), 135)
        by_session = {}
        for row in arrivals:
            by_session.setdefault(row["session_id"], []).append(row["turn_id"])
            self.assertGreater(row["unit_exponential_gap"], 0)
        self.assertTrue(all(turns == list(range(1, 10)) for turns in by_session.values()))

    def test_selection_and_arrivals_are_deterministic(self):
        first = select_sessions(self._pool(), 3, 27001)
        second = select_sessions(self._pool(), 3, 27001)
        self.assertEqual(first, second)
        self.assertEqual(build_arrivals(first, 10, 27002), build_arrivals(second, 10, 27002))

    def test_locality_variant_shares_stable_only(self):
        sessions = select_sessions(self._pool(per_family=5), 5, 27001)
        for index, row in enumerate(sessions):
            row["tsc_session_id"] = f"session-{index}"
            row["tenant_id"] = f"tenant-{index}"
            row["segments"] = [
                {"type": "RAG_CHUNK", "text": f"stable-{index}", "token_count": 2},
                {"type": "USER_QUERY", "text": f"private-{index}", "token_count": 2},
            ]
        output = variant(sessions, 5)
        first_family = [row for row in output if row["tsc_family"] == "RULER"]
        self.assertEqual(len({row["service_template_id"] for row in first_family}), 1)
        self.assertEqual(len({stable_segments(row)[0]["text"] for row in first_family}), 1)
        private = [next(segment["text"] for segment in row["segments"] if segment["type"] == "USER_QUERY")
                   for row in first_family]
        self.assertEqual(len(set(private)), 5)

    def test_quality_templates_preserve_semantics_and_fan_out_identity(self):
        sessions = select_sessions(self._pool(per_family=2), 2, 27001)
        for index, row in enumerate(sessions):
            row["answer"] = f"answer-{index}"
            row["segments"] = [
                {"type": "RAG_CHUNK", "text": f"context-{index}", "token_count": 2},
                {"type": "USER_QUERY", "text": f"query-{index}", "token_count": 2},
            ]
        output = build_quality_templates(sessions, tenants_per_template=3)
        self.assertEqual(len(output), 15)
        for family in FAMILIES:
            group = [row for row in output if row["tsc_family"] == family]
            self.assertEqual(len({row["service_template_id"] for row in group}), 1)
            self.assertEqual(len({json.dumps(row["segments"], sort_keys=True) for row in group}), 1)
            self.assertEqual(len({str(row["answer"]) for row in group}), 1)
            self.assertEqual(len({row["tenant_id"] for row in group}), 3)

    def test_active_template_variant_and_arrivals_preserve_invariants(self):
        sessions = select_sessions(self._pool(per_family=25), 25, 27001)
        for index, row in enumerate(sessions):
            row["tsc_session_id"] = f"session-{index:03d}"
            row["segments"] = [
                {"type": "RAG_CHUNK", "text": f"stable-{index}", "token_count": 2},
                {"type": "USER_QUERY", "text": f"private-{index}", "token_count": 2},
            ]
        output = variant_template_count(sessions, 25)
        self.assertEqual(len(output), 125)
        self.assertEqual(len({row["service_template_id"] for row in output}), 25)
        self.assertEqual(
            {next(segment["text"] for segment in row["segments"] if segment["type"] == "USER_QUERY")
             for row in output},
            {f"private-{index}" for index in range(125)},
        )
        gaps = [float(index + 1) / 1000 for index in range(1125)]
        round_robin = build_residency_arrivals(output, gaps, "round_robin", 27101)
        zipf = build_residency_arrivals(output, gaps, "zipf", 27102)
        self.assertEqual([row["unit_exponential_gap"] for row in round_robin], gaps)
        self.assertEqual([row["unit_exponential_gap"] for row in zipf], gaps)
        self.assertEqual(round_robin, build_residency_arrivals(output, gaps, "round_robin", 27101))
        self.assertEqual(zipf, build_residency_arrivals(output, gaps, "zipf", 27102))
        self.assertEqual(len({row["service_template_id"] for row in round_robin}), 25)

    def test_registration_scope_tracks_service_object(self):
        sample = {"tsc_session_id": "session-a", "service_template_id": "template-a"}
        session_args = SimpleNamespace(certificate_scope_mode="qualified_session")
        template_args = SimpleNamespace(certificate_scope_mode="service_template")
        self.assertEqual(registration_scope(session_args, sample), "session-a")
        self.assertEqual(registration_scope(template_args, sample), "template-a")

    def test_cache_salt_matches_certificate_scope_without_weakening_native_trace(self):
        sample = {"tsc_session_id": "session-a", "service_template_id": "template-a"}
        native = SimpleNamespace(certificate_scope_mode="qualified_session", policy="D0-native-apc",
                                 policy_hash="policy-a")
        session_contract = SimpleNamespace(certificate_scope_mode="qualified_session",
                                           cache_scope_mode="certificate", policy="D2-full-contractkv", policy_hash="policy-a")
        template_native = SimpleNamespace(certificate_scope_mode="service_template", policy="D0-native-apc",
                                          policy_hash="policy-a")
        self.assertIsNone(request_cache_salt(native, sample))
        self.assertEqual(request_cache_salt(session_contract, sample), "policy-a:session-a")
        self.assertEqual(request_cache_salt(template_native, sample), "policy-a:template-a")
        session_certificate_shared_cache = SimpleNamespace(
            certificate_scope_mode="qualified_session", cache_scope_mode="service_template",
            policy="D2-full-contractkv", policy_hash="policy-a")
        self.assertEqual(request_cache_salt(session_certificate_shared_cache, sample), "policy-a:template-a")

    def test_queue_slope(self):
        self.assertAlmostEqual(slope([0, 1, 2], [0, 1, 2]), 1.0)
        self.assertEqual(slope([1], [2]), 0.0)

    def test_tenant_scope_assignment_and_fairness(self):
        tenants = tenant_specs(40, 0.5)
        self.assertEqual(sum(row["allowed_shared"] for row in tenants), 20)
        self.assertEqual(len({row["tenant_id"] for row in tenants}), 40)
        self.assertEqual(len({row["scope_id"] for row in tenants if row["allowed_shared"]}), 1)
        self.assertAlmostEqual(jain([1.0, 1.0, 1.0]), 1.0)

    def test_tenant_completion_uses_offered_requests_as_denominator(self):
        tenants = tenant_specs(2, 0.0)
        row = {
            "success": True, "metric_join_success": True,
            "tenant_id": tenants[0]["tenant_id"], "service_class": tenants[0]["service_class"],
            "turn_id": 1, "scope_id": tenants[0]["scope_id"], "ttft_ms": 1,
            "slo_ms": 3000, "quality_sanity": True, "wave_wall_ms": 1,
            "effective_policy": "raw-order", "used_gpu_blocks": 1, "free_gpu_blocks": 1,
            "newly_allocated_blocks": 1, "scheduler_waiting_requests": 0,
            "reused_physical_blocks": 0, "physical_block_hashes": [],
            "prefix_hit_tokens": 0, "allowed_prefix_tokens": 0, "block_size": 16,
            "scope_check_pass": True, "scope_check_ms": .01, "effective_policy": "raw-order",
        }
        args = SimpleNamespace(tenants=2, turns=2, cell_id="test", policy="raw-order", sharing_ratio=0.0)
        summary = summarize_tenants(args, [row], tenants, {
            "allowed_refcount_match_rate": 1.0, "concurrent_shared_blocks": 0,
        })
        self.assertEqual(summary[0]["completion_rate"], 0.5)

    def test_lifecycle_mutation_changes_only_target_field(self):
        original = baseline_scope("tenant-a", 1)
        changed = mutate(original, "policy_hash")
        self.assertNotEqual(original["policy_hash"], changed["policy_hash"])
        for key in original:
            if key != "policy_hash":
                self.assertEqual(original[key], changed[key])
        source = Path("scripts/tsc_service_lifecycle_live.py").read_text(encoding="utf-8")
        self.assertIn('cache_salt=f"tsc-lifecycle:{digest(scope)}"', source)
        self.assertIn("cross_version = old_hashes & affected_hashes", source)

    def test_economics_has_twelve_live_points_and_contour_regions(self):
        self.assertEqual(len(BOUNDARY_POINTS), 12)
        rows = []
        for length in (1000, 2000, 4000, 6000):
            rows.append({"model_identity": "test", "stable_prefix_tokens": length,
                         "saved_ms_per_turn": length / 10, "registration_ms": 250})
        output = contour(rows)
        self.assertEqual(len(output), 64)
        self.assertIn("positive", {row["operating_region"] for row in output})
        self.assertIn("tool-slack-hidden", {row["operating_region"] for row in output})
        source = Path("scripts/tsc_verification_economics_live.py").read_text(encoding="utf-8")
        self.assertIn('attestation_mode="prospective-qualified-template-exact-path-v1"', source)
        self.assertIn("args.registration_max_tokens", source)
        self.assertIn("effective_layout = compiled if certificate_issued else raw", source)

    def test_economics_certificate_gate_accepts_fail_closed_rejection(self):
        self.assertTrue(certificate_outcome_consistent({
            "certificate_issued": True, "verify_decision": "PASS",
            "txn_state": "COMMITTED", "effective_policy": "compiled",
        }))
        self.assertTrue(certificate_outcome_consistent({
            "certificate_issued": False, "verify_decision": "FAIL",
            "txn_state": "ABORTED", "effective_policy": "raw-fallback",
        }))
        self.assertFalse(certificate_outcome_consistent({
            "certificate_issued": False, "verify_decision": "FAIL",
            "txn_state": "ABORTED", "effective_policy": "compiled",
        }))

    def test_slo_capacity_requires_all_three_fresh_repeats(self):
        rows = []
        for repeat in (1, 2, 3):
            rows.append({"model": "qwen", "policy": "D0-native-apc", "repeat": repeat,
                         "tenants_per_template": 25, "slo_ttft_ms": 1500,
                         "load_fraction": 1.0, "completion_rate": 1.0,
                         "quality_sanity_rate": 1.0, "p99_ttft_ms": 1400,
                         "timeout_or_drop_rate": 0.0})
        output = locality_capacity(rows)
        self.assertEqual(output[0]["slo_sustainable_load_fraction"], 1.0)
        rows[-1]["p99_ttft_ms"] = 1600
        self.assertEqual(locality_capacity(rows)[0]["slo_sustainable_load_fraction"], 0.0)

    def test_paper_renderer_omits_zero_denominator_capacity_claim(self):
        source = Path("scripts/render_tsc_service_reports.py").read_text(encoding="utf-8")
        self.assertNotIn('read_csv(root / "service_locality_slo_capacity_v0.csv")', source)
        self.assertNotIn('"## SLO-sustainable service capacity"', source)
        self.assertIn("deployment operating-region analysis", source)

    def test_quality_runner_verifies_the_turn_zero_prepared_object(self):
        source = Path("scripts/tsc_service_template_quality_live.py").read_text(encoding="utf-8")
        self.assertIn('prepared[str(representative["tsc_session_id"])][0]', source)

    def test_quality_runner_fails_closed_for_unqualified_template(self):
        protocol = json.loads(Path("configs/tsc_service_quality_protocol.json").read_text(encoding="utf-8"))
        self.assertFalse(protocol["template_qualification"]["Qasper"])
        self.assertTrue(all(protocol["template_qualification"][family]
                            for family in FAMILIES if family != "Qasper"))
        source = Path("scripts/tsc_service_template_quality_live.py").read_text(encoding="utf-8")
        self.assertIn('"FROZEN_RAW_FALLBACK"', source)
        self.assertIn('if compiled else None', source)

    def test_shadow_parking_never_requeues_a_running_request(self):
        source = Path("scripts/install_vllm_v1_ephemeral_shadow_hook.py").read_text(encoding="utf-8")
        start = source.index("def _contractkv_park_and_wake")
        end = source.index("def _contractkv_should_admit_shadow", start)
        helper = source[start:end]
        self.assertNotIn("scheduler.running[:]", helper)
        self.assertNotIn("for request in scheduler.running", helper)

    def test_locality_runner_uses_one_policy_hash_for_server_and_client(self):
        source = Path("scripts/run_tsc_service_locality_sweep.sh").read_text(encoding="utf-8")
        expected = "tsc-locality-$label-g$level-v0"
        self.assertEqual(source.count(expected), 2)
        self.assertIn("cache_scope_mode=service_template", source)
        self.assertIn("attestation_mode=prospective-qualified", source)

    def test_locality_pilot_gate_requires_real_template_attestation(self):
        common = {
            "offered_requests": 1125, "completion_rate": 1.0, "quality_sanity_rate": 1.0,
            "scope_check_pass_rate": 1.0, "private_suffix_exclusion_rate": 1.0,
            "unauthorized_cross_domain_reused_hashes": 0, "dynamic_suffix_reuse_blocks": 0,
            "mean_scope_check_ms": .01, "unhidden_verification_ms_per_future_request": 0,
        }
        d0 = {**common, "mean_ttft_ms": 800, "mean_new_prefill_tokens": 2200}
        d1 = {**common, "mean_ttft_ms": 60, "mean_new_prefill_tokens": 40}
        d2 = {**common, "mean_ttft_ms": 65, "mean_new_prefill_tokens": 41,
              "actual_verifier_endpoint_calls": 5, "transaction_commits": 5}
        self.assertTrue(evaluate_locality_pilot(d0, d1, d2)["gate_pass"])
        d2["actual_verifier_endpoint_calls"] = 125
        self.assertFalse(evaluate_locality_pilot(d0, d1, d2)["gate_pass"])

    def test_multi_tenant_uses_template_exact_path_attestation(self):
        source = Path("scripts/tsc_multi_tenant_live.py").read_text(encoding="utf-8")
        self.assertIn('"attestation_mode": "prospective-qualified-template-exact-path-v1"', source)
        self.assertIn("args.registration_max_tokens", source)
        self.assertIn("scope_check_pass", source)

    def test_shell_runners_do_not_expand_a_local_before_assignment(self):
        for path in (
            Path("scripts/run_tsc_residency_sweep.sh"),
            Path("scripts/run_tsc_multi_tenant.sh"),
        ):
            for line in path.read_text(encoding="utf-8").splitlines():
                if "local tag=" in line:
                    self.assertNotIn('dir="$OUT/$tag"', line)


if __name__ == "__main__":
    unittest.main()
