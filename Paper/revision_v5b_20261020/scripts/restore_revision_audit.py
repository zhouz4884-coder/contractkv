"""Restore V4 additions from frozen CPU records, without model calls or selection."""
from pathlib import Path
from collections import defaultdict
import csv
import hashlib
import json
import math
import statistics

ROOT = Path(__file__).resolve().parents[1]
E = ROOT / "evidence"


def rows(name):
    with (E / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(a, b):
    assert abs(float(a) - float(b)) < 1e-7, (a, b)


def percentile(values, fraction):
    values = sorted(values)
    at = (len(values) - 1) * fraction
    lower = int(math.floor(at))
    return values[lower] + (values[min(lower + 1, len(values) - 1)] - values[lower]) * (at - lower)


def table(caption, label, columns, heading, content, wide=False):
    environment = "table*" if wide else "table"
    return (
        f"\\begin{{{environment}}}[t]\n\\centering\\small\n"
        f"\\caption{{{caption}}}\n\\label{{{label}}}\n"
        f"\\begin{{tabular}}{{@{{}}{columns}@{{}}}}\n\\toprule\n"
        + heading + "\\\\\n\\midrule\n"
        + "\n".join(" & ".join(map(str, row)) + r"\\" for row in content)
        + f"\n\\bottomrule\n\\end{{tabular}}\n\\end{{{environment}}}\n"
    )


def main():
    utility = json.loads((E / "faithful_utility_audit_v1.json").read_text())
    assert utility["paired_business_csv_sha256"] == sha(E / "faithful_all_business_quality_v1.csv")
    assert utility["new_GPU_requests"] == 0
    quality = rows("faithful_all_business_quality_v1.csv")
    latency = rows("faithful_request_latency_pairs_v1.csv")
    assert len(quality) == len(latency) == 5400
    key = lambda row: tuple(row[k] for k in ("model", "policy", "repeat", "source_group", "session_id", "turn_id"))
    latency_index = {key(row): row for row in latency}
    assert len(latency_index) == 5400 and set(latency_index) == {key(row) for row in quality}
    groups = defaultdict(list)
    for row in quality:
        if row["row_type"] == "future":
            groups[row["model"], row["source_group"]].append(row)
    assert len(groups) == 18 and sum(map(len, groups.values())) == 4860
    source_ids = sorted({row["source_group"] for row in quality})
    assert len(source_ids) == 6
    aliases = {}
    for family, prefix in [("HotpotQA", "H"), ("RepoBench", "R")]:
        selected = sorted(row["source_group"] for row in utility["source_metadata"] if row["family"] == family)
        assert len(selected) == 3
        aliases.update({identity: f"{prefix}{i}" for i, identity in enumerate(selected, 1)})
    metadata = {row["source_group"]: row for row in utility["source_metadata"]}
    utilities = {(r["model"], r["source_group"]): r for r in utility["source_model_population_results"] if r["population"] == "future"}
    labels = {"Qwen3-8B": "Qwen", "Mistral-7B-Instruct-v0.3": "Mistral", "Llama-3.1-8B-Instruct": "Llama"}
    output = []
    for source in sorted(source_ids, key=lambda value: aliases[value]):
        for model in labels:
            pair = groups[model, source]
            assert len(pair) == 270 and {r["repeat"] for r in pair} == {"1", "2", "3"}
            compiled = [r for r in pair if r["effective_level"] != "L0"]
            assert all(int(r["first_output_ID_divergence"]) == -1 and float(r["quality_drop"]) == 0 for r in compiled)
            reference = statistics.fmean(float(r["raw_score"]) for r in pair)
            strategy = statistics.fmean(float(r["policy_score"]) for r in pair)
            positive = sum(float(r["raw_score"]) > 0 for r in compiled)
            increases = sum(float(r["quality_drop"]) < -.03 for r in pair)
            decreases = sum(float(r["quality_drop"]) > .03 for r in pair)
            u = utilities[model, source]
            close(reference, u["raw_mean_frozen_score"])
            close(strategy, u["policy_mean_frozen_score"])
            assert len(compiled) == u["compiled_answers"] and positive == u["compiled_positive_frozen_score_answers"]
            assert (increases, decreases) == (u["all_route_material_improvements"], u["all_route_material_drops"])
            lr = [latency_index[key(r)] for r in pair]
            raw_p99 = percentile([float(r["raw_ready_ttft_ms"]) for r in lr], .99)
            ckv_p99 = percentile([float(r["ready_ttft_ms"]) for r in lr], .99)
            frozen = [r for r in rows("faithful_latency_strata_v1.csv") if r["stratum"] == "template" and r["model"] == model and r["value"] == source]
            assert len(frozen) == 1
            close(raw_p99, frozen[0]["raw_ready_ttft_ms_p99"])
            close(ckv_p99, frozen[0]["ready_ttft_ms_p99"])
            output.append({"source": aliases[source], "source_group": source, "model": labels[model],
                "future_pairs": len(pair), "compiled": len(compiled), "raw_mean_score": reference,
                "mean_score_delta": strategy-reference, "compiled_raw_positive": positive,
                "material_increases": increases, "material_decreases": decreases,
                "raw_ready_p99_ms": raw_p99, "CKV_ready_p99_ms": ckv_p99})
    assert sum(r["compiled"] for r in output) == 1296
    body = [[r["source"], r["model"], f'{r["raw_mean_score"]:.6f}', f'{r["mean_score_delta"]:+.6f}',
             f'{r["compiled"]}/270', f'{r["compiled_raw_positive"]}/{r["compiled"]}' if r["compiled"] else '--',
             f'{r["material_increases"]}/{r["material_decreases"]}',
             f'{r["raw_ready_p99_ms"]:,.1f} $\\rightarrow$ {r["CKV_ready_p99_ms"]:,.1f}'] for r in output]
    source_table = table(
        'All six primary sources, with three process repetitions nested within each source/model. Each row has 270 future pairs. Scores use the frozen task adapter; $\\Delta$ is the all-route strategy-minus-raw mean. C denotes compiled pairs; positive credit is counted within C. Increases/decreases use $|\\Delta s|>0.03$. p99 is recomputed over that row\'s paired future readiness times, including qualification waiting; these are point estimates, not independent-source confidence intervals.',
        'tab:s-source-results', 'llrrrrrr',
        r'Source & Model & Raw mean & $\Delta$ mean & C / pairs & Raw $>0$ / C & Up/down & p99 raw $\rightarrow$ CKV (ms)', body, True)
    hotpot = sorted((s for s in source_ids if aliases[s].startswith('H')), key=lambda s: aliases[s])
    repo = sorted((s for s in source_ids if aliases[s].startswith('R')), key=lambda s: aliases[s])
    mapping = [
        'H1/H2/H3 are HotpotQA documents '+ '/'.join(s.split(':')[-1] for s in hotpot) +
        ', respectively. H1 retains full text; H2/H3 crop only optional context.',
        'R1/R2/R3 are the RepoBench Python v1.1 repositories '+
        ', '.join(r'\path{'+s.split(':')[-1]+'}' for s in repo) +
        ', respectively, all retained in full. Canonical source keys and input hashes accompany the frozen record.'
    ]

    cases = rows('registration_manifest_cases_v1.csv')
    assert len(cases) == 9 and sum(r['actual_reject'] == 'True' for r in cases) == 7
    names = {
        'authorized_template': ('Authorized operator template', 'Accept', 'Consistent authorized declaration'),
        'untrusted_client_reuses_operator_manifest': ('Tenant attempts shared registration', 'Reject', 'No operator registration authority'),
        'forged_operator_identity': ('Forged operator identity', 'Reject', 'Issuer/tag mismatch'),
        'changed_content_stale_hash': ('Changed bytes, stale hash', 'Reject', 'Content identity mismatch'),
        'explicit_private_publication': ('Explicit tenant-private publication', 'Reject', 'Declared visibility conflicts with publication'),
        'mutable_shared_segment': ('Mutable segment marked for publication', 'Reject', 'Declared stability conflicts with publication'),
        'missing_authorization': ('Missing authorization domain', 'Reject', 'Required registration scope absent'),
        'stale_signed_version': ('Version changed under old tag', 'Reject', 'Authenticated binding changed'),
        'trusted_operator_mislabels_private_as_public': ('Trusted operator mislabels private bytes', 'Accept', 'Valid declaration; confidentiality not inferred'),
    }
    case_table = table('Nine frozen CPU registration-helper cases: seven rejects, one legitimate acceptance and one accepted semantic mislabel. The helper validates declaration authority/consistency, does not infer confidentiality, and is not integrated into the live endpoint.',
        'tab:s-manifest', 'P{6.0cm}lP{8.0cm}', 'Case & Result & Interpretation', [names[r['case']] for r in cases], True)

    ci = [r for r in rows('service_locality_confidence_intervals_v0.csv') if r['model'] == 'qwen' and r['tenants_per_template'] == '25' and float(r['load_fraction']) == .8 and float(r['slo_ttft_ms']) == 500]
    assert len(ci) == 1
    ci = ci[0]
    aggregate = rows('service_locality_aggregate_v0.csv')
    for policy, field in [('D0-native-apc', 'raw_slo_goodput_rps'), ('D2-template-contractkv', 'contract_slo_goodput_rps')]:
        selected = [r for r in aggregate if r['model'] == 'qwen' and r['policy'] == policy and r['tenants_per_template'] == '25' and float(r['load_fraction']) == .8 and float(r['slo_ttft_ms']) == 500]
        assert len(selected) == 1
        close(ci[field], selected[0]['mean_slo_compliant_goodput_rps'])
    close(float(ci['contract_slo_goodput_rps'])-float(ci['raw_slo_goodput_rps']), ci['slo_goodput_delta_rps'])
    assert ci['resampling_units'] == 'fresh_process/service_template/tenant_session'
    assert int(ci['cluster_bootstrap_iterations']) == 10000
    ci_table = table('Archived Qwen deployment-template open-arrival point: 25 tenants/template, 80\\% calibrated load, 500-ms SLO. Goodput units are requests/s. The 95\\% percentile interval resamples fresh processes, service templates and tenant sessions hierarchically (10,000 draws); it is not a three-process min--max or a confidence interval across qualification protocols.',
        'tab:s-open-ci', 'rrrr', 'Raw & ContractKV & Increase & 95\\% interval', [[f"{float(ci['raw_slo_goodput_rps']):.6f}", f"{float(ci['contract_slo_goodput_rps']):.6f}", f"{float(ci['slo_goodput_delta_rps']):.6f}", f"[{float(ci['slo_goodput_delta_ci_low']):.6f}, {float(ci['slo_goodput_delta_ci_high']):.6f}]"]])
    tex = r'''\section{Source-Level Outcomes and Registration Boundaries}
\label{sec:s-audit}
Table~\ref{tab:s-source-results} retains every source from the frozen primary cohort. No source or score was filtered after generation. It separates absolute reference utility, all-route score changes, compiled coverage and source-level tails. The common denominator does not make tenant or process observations independent content sources.

'''+source_table+'\n'+r'\paragraph{Source identities and input status.}'+'\n'+'\n'.join(mapping)+r'''

\subsection{Registration Trust Boundary}
Table~\ref{tab:s-manifest} lists every frozen helper case. Identity, role, authentication, hash and declared-publication checks cannot infer whether trusted shared-content declarations are semantically correct. A valid hash/tag on a private tool response mislabeled shared remains an operator error. The live endpoint and PSTP controls are separate evidence, not an end-to-end disclosure detector.

'''+case_table+r'''
\subsection{Open-Arrival Uncertainty}
Table~\ref{tab:s-open-ci} gives the absolute goodput increment at the main figure's deployment operating point. Its percentile interval uses 10,000 hierarchical resamples of fresh processes, service templates and tenant sessions, with each process's measured service duration as denominator. It concerns this open-arrival trace, not the query-qualified closed-loop cohort.

'''+ci_table
    (ROOT/'sections/supplement_revision_audit.tex').write_text(tex, encoding='utf-8')
    origins = json.loads((ROOT/'audit/revision_input_sources.json').read_text())
    report = {'source_rows': output, 'manifest_cases': cases, 'open_arrival_interval': ci,
        'source_files': [{'file': name, 'origin': origin, 'sha256': sha(E/name)} for name, origin in origins.items()],
        'new_model_calls': 0, 'new_sources_selected': 0,
        'bootstrap_rerun': False, 'CI_status': 'Restored archived interval; aggregate point values cross-checked',
        'future_pairs': 4860, 'compiled_future_pairs': 1296,
        'source_level_p99_recomputed_and_cross_checked': True}
    (E/'revision_audit_evidence.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'source_model_rows': len(output), 'future_pairs': 4860, 'compiled': 1296,
        'manifest_cases': len(cases), 'open_goodput_delta_ci': [ci['slo_goodput_delta_ci_low'], ci['slo_goodput_delta_ci_high']]}))


if __name__ == '__main__':
    main()
