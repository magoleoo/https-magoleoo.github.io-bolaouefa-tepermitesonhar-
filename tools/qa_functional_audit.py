#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Tuple

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
except Exception as exc:  # pragma: no cover - tratado em runtime no ambiente do usuário
    print(
        "Erro: Playwright não está disponível.\n"
        "Instale com:\n"
        "  python3 -m pip install playwright\n"
        "  python3 -m playwright install chromium\n"
        f"\nDetalhe técnico: {exc}",
        file=sys.stderr,
    )
    raise SystemExit(2)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class CheckResult:
    scope: str
    id: str
    name: str
    status: str  # PASS | FAIL | WARN
    critical: bool
    details: str = ""


def pass_check(scope: str, check_id: str, name: str, details: str = "", critical: bool = True) -> CheckResult:
    return CheckResult(scope=scope, id=check_id, name=name, status="PASS", critical=critical, details=details)


def fail_check(scope: str, check_id: str, name: str, details: str = "", critical: bool = True) -> CheckResult:
    return CheckResult(scope=scope, id=check_id, name=name, status="FAIL", critical=critical, details=details)


def warn_check(scope: str, check_id: str, name: str, details: str = "", critical: bool = False) -> CheckResult:
    return CheckResult(scope=scope, id=check_id, name=name, status="WARN", critical=critical, details=details)


def browser_time_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_default_url() -> str:
    index_path = PROJECT_ROOT / "index.html"
    return index_path.resolve().as_uri()


def is_active_panel(page, panel_selector: str) -> bool:
    return bool(page.locator(panel_selector).evaluate("el => el.classList.contains('is-active')"))


def bypass_login(page) -> Tuple[str, str]:
    modal = page.locator("#login-modal")
    if not modal.count() or not modal.is_visible():
        return "WARN", "Modal não visível (acesso sem senha já ativo/localStorage)."

    skip = page.locator("#skip-login-button")
    if skip.count() and skip.is_visible():
        skip.click()
        page.wait_for_timeout(900)
        return "PASS", "Entrada feita com 'Entrar sem identificar'."

    user_input = page.locator("#login-user")
    submit = page.locator("#login-form button.primary-button")
    if user_input.count() and submit.count() and submit.is_visible():
        user_input.fill("Felippe Leite")
        submit.click()
        page.wait_for_timeout(900)
        return "PASS", "Entrada feita preenchendo nome e clicando continuar."

    return "FAIL", "Modal visível, mas não foi possível concluir o fluxo de entrada."


def collect_console(page, bucket: List[str], scope: str) -> None:
    page.on(
        "console",
        lambda msg: bucket.append(f"{scope}:{msg.type}: {msg.text}") if msg.type == "error" else None,
    )
    page.on("pageerror", lambda err: bucket.append(f"{scope}:pageerror: {err}"))


def run_desktop_checks(page, checks: List[CheckResult]) -> None:
    scope = "desktop"
    page.wait_for_timeout(1100)

    login_status, login_details = bypass_login(page)
    if login_status == "PASS":
        checks.append(pass_check(scope, "desktop_login", "Fluxo de entrada", login_details))
    elif login_status == "WARN":
        checks.append(warn_check(scope, "desktop_login", "Fluxo de entrada", login_details))
    else:
        checks.append(fail_check(scope, "desktop_login", "Fluxo de entrada", login_details))

    ranking_rows = page.locator("#ranking-table tr").count()
    checks.append(
        pass_check(scope, "desktop_ranking", "Aba Ranking", f"Linhas no ranking: {ranking_rows}")
        if ranking_rows > 0
        else fail_check(scope, "desktop_ranking", "Aba Ranking", "Tabela sem linhas.")
    )

    page.locator("#tab-results").click()
    page.wait_for_timeout(700)
    top8 = page.locator("#top-8-grid > *").count()
    result_tabs = page.locator("#results-tabs .tab-button").count()
    result_cards = page.locator("#matches-list .match-card, #matches-list .phase-block").count()
    ok_results = top8 > 0 and result_tabs >= 6 and result_cards > 0
    checks.append(
        pass_check(
            scope,
            "desktop_results",
            "Aba Resultados",
            f"top8={top8}, subtabs={result_tabs}, cards={result_cards}",
        )
        if ok_results
        else fail_check(
            scope,
            "desktop_results",
            "Aba Resultados",
            f"top8={top8}, subtabs={result_tabs}, cards={result_cards}",
        )
    )

    page.locator("#tab-superclassic").click()
    page.wait_for_timeout(800)
    sc_tables = page.locator("#panel-superclassic .superclassic-matrix-table").count()
    sc_rows = page.locator("#panel-superclassic .superclassic-matrix-table tbody tr").count()
    trend_hits = page.locator("#panel-superclassic .superclassic-trend-hit").count()
    exact_hits = page.locator("#panel-superclassic .superclassic-exact-hit").count()
    ok_sc = sc_tables > 0 and sc_rows > 1
    checks.append(
        pass_check(
            scope,
            "desktop_superclassic",
            "Aba Superclássicos",
            f"tabelas={sc_tables}, linhas={sc_rows}, trend={trend_hits}, exact={exact_hits}",
        )
        if ok_sc
        else fail_check(
            scope,
            "desktop_superclassic",
            "Aba Superclássicos",
            f"tabelas={sc_tables}, linhas={sc_rows}",
        )
    )

    page.locator("#tab-predictions").click()
    page.wait_for_timeout(900)
    pred_tables = page.locator("#panel-predictions .predictions-matrix-table").count()
    export_button = page.locator("#predictions-export-pdf")
    export_enabled = export_button.count() and export_button.is_enabled()
    ok_pred = pred_tables > 0 and bool(export_enabled)
    checks.append(
        pass_check(
            scope,
            "desktop_predictions",
            "Aba Palpites",
            f"tabelas={pred_tables}, export_enabled={bool(export_enabled)}",
        )
        if ok_pred
        else fail_check(
            scope,
            "desktop_predictions",
            "Aba Palpites",
            f"tabelas={pred_tables}, export_enabled={bool(export_enabled)}",
        )
    )

    pdf_ok = False
    pdf_details = ""
    try:
        with page.expect_popup(timeout=7000) as popup_wait:
            export_button.click()
        popup = popup_wait.value
        popup.wait_for_load_state("domcontentloaded", timeout=7000)
        has_preview_image = popup.locator('img[alt="Tabela de palpites"]').count() > 0
        has_sheet_class = popup.locator(".sheet").count() > 0
        pdf_ok = has_preview_image and has_sheet_class
        pdf_details = f"title={popup.title()}, preview={has_preview_image}, sheet={has_sheet_class}"
        popup.close()
    except PlaywrightTimeoutError:
        pdf_ok = False
        pdf_details = "Popup de exportação não abriu dentro do timeout."

    checks.append(
        pass_check(scope, "desktop_pdf", "Exportar PDF", pdf_details)
        if pdf_ok
        else fail_check(scope, "desktop_pdf", "Exportar PDF", pdf_details)
    )

    page.locator("#tab-history").click()
    page.wait_for_timeout(700)
    history_rows = page.locator("#history-table tr").count()
    hall_rows = page.locator("#hall-of-fame table tbody tr").count()
    ok_history = history_rows > 0 and hall_rows > 0
    checks.append(
        pass_check(
            scope,
            "desktop_history",
            "Aba Histórico",
            f"history_rows={history_rows}, hall_rows={hall_rows}",
        )
        if ok_history
        else fail_check(
            scope,
            "desktop_history",
            "Aba Histórico",
            f"history_rows={history_rows}, hall_rows={hall_rows}",
        )
    )

    page.locator("#tab-rules").click()
    page.wait_for_timeout(700)
    rules_cards = page.locator("#rules-panel .rules-card").count()
    checks.append(
        pass_check(scope, "desktop_rules", "Aba Regras", f"cards={rules_cards}")
        if rules_cards > 0
        else fail_check(scope, "desktop_rules", "Aba Regras", "Sem cards de regras visíveis.")
    )


def run_mobile_checks(page, checks: List[CheckResult]) -> None:
    scope = "mobile"
    page.wait_for_timeout(1200)

    login_status, login_details = bypass_login(page)
    if login_status == "PASS":
        checks.append(pass_check(scope, "mobile_login", "Fluxo de entrada", login_details))
    elif login_status == "WARN":
        checks.append(warn_check(scope, "mobile_login", "Fluxo de entrada", login_details))
    else:
        checks.append(fail_check(scope, "mobile_login", "Fluxo de entrada", login_details))

    picker = page.locator("#mobile-tab-select")
    if picker.count() and picker.is_visible():
        checks.append(pass_check(scope, "mobile_picker", "Seletor mobile de abas", "Seletor visível."))
    else:
        checks.append(fail_check(scope, "mobile_picker", "Seletor mobile de abas", "Seletor não encontrado/visível."))
        return

    map_panel = {
        "ranking": "#panel-ranking",
        "results": "#panel-results",
        "superclassic": "#panel-superclassic",
        "predictions": "#panel-predictions",
        "history": "#panel-history",
        "rules": "#panel-rules",
    }

    tabs = [
        ("ranking", "Ranking"),
        ("results", "Resultados"),
        ("superclassic", "Superclássicos"),
        ("predictions", "Palpites"),
        ("history", "Histórico"),
        ("rules", "Regras"),
    ]

    for value, label in tabs:
        picker.select_option(value)
        page.wait_for_timeout(850)
        is_active = is_active_panel(page, map_panel[value])

        ok = bool(is_active)
        detail = "painel ativo"
        check_id = f"mobile_tab_{value}"

        if value == "ranking":
            rows = page.locator("#ranking-table tr").count()
            ok = ok and rows > 0
            detail = f"rows={rows}"
        elif value == "results":
            top8 = page.locator("#top-8-grid > *").count()
            ok = ok and top8 > 0
            detail = f"top8={top8}"
        elif value == "superclassic":
            cards = page.locator("#panel-superclassic .superclassic-mobile-board .prediction-mobile-match").count()
            ok = ok and cards > 0
            detail = f"mobile_cards={cards}"
        elif value == "predictions":
            cards = page.locator("#panel-predictions .predictions-mobile-board .prediction-mobile-match").count()
            ok = ok and cards > 0
            detail = f"mobile_cards={cards}"
        elif value == "history":
            rows = page.locator("#history-table tr").count()
            ok = ok and rows > 0
            detail = f"rows={rows}"
        elif value == "rules":
            cards = page.locator("#rules-panel .rules-card").count()
            ok = ok and cards > 0
            detail = f"cards={cards}"

        checks.append(
            pass_check(scope, check_id, f"Aba mobile: {label}", detail)
            if ok
            else fail_check(scope, check_id, f"Aba mobile: {label}", detail)
        )


def summarize_scope(checks: List[CheckResult], scope: str) -> Dict[str, int]:
    scoped = [item for item in checks if item.scope == scope]
    passed = sum(1 for item in scoped if item.status == "PASS")
    failed = sum(1 for item in scoped if item.status == "FAIL")
    warned = sum(1 for item in scoped if item.status == "WARN")
    critical_total = sum(1 for item in scoped if item.critical)
    critical_failed = sum(1 for item in scoped if item.critical and item.status == "FAIL")
    return {
        "total": len(scoped),
        "passed": passed,
        "failed": failed,
        "warned": warned,
        "critical_total": critical_total,
        "critical_failed": critical_failed,
    }


def build_markdown(report: Dict[str, object]) -> str:
    lines: List[str] = []
    lines.append("# Auditoria Funcional Guiada")
    lines.append("")
    lines.append(f"- Data UTC: `{report['generated_at_utc']}`")
    lines.append(f"- URL auditada: `{report['target_url']}`")
    lines.append("")

    overall = report["overall"]
    lines.append("## Resultado geral")
    lines.append("")
    lines.append(
        f"- Status: **{'OK' if overall['ok'] else 'FALHA'}** "
        f"(críticos falhos: {overall['critical_failed']}/{overall['critical_total']})"
    )
    lines.append(f"- Erros de runtime/console: `{overall['runtime_errors']}`")
    lines.append("")

    for scope in ("desktop", "mobile"):
        summary = report["summary"][scope]
        lines.append(f"## {scope.capitalize()}")
        lines.append("")
        lines.append(
            f"- Checks: `{summary['passed']}/{summary['total']}` PASS, "
            f"`{summary['failed']}` FAIL, `{summary['warned']}` WARN"
        )
        lines.append(
            f"- Críticos: `{summary['critical_total'] - summary['critical_failed']}/{summary['critical_total']}` PASS"
        )
        lines.append("")
        lines.append("| ID | Check | Status | Detalhes |")
        lines.append("| --- | --- | --- | --- |")
        for check in [item for item in report["checks"] if item["scope"] == scope]:
            lines.append(
                f"| `{check['id']}` | {check['name']} | **{check['status']}** | {check['details']} |"
            )
        lines.append("")

    runtime_errors = report.get("runtime_errors", [])
    if runtime_errors:
        lines.append("## Runtime / Console")
        lines.append("")
        for err in runtime_errors:
            lines.append(f"- `{err}`")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Auditoria funcional guiada do bolão (desktop + mobile, aba por aba)."
    )
    parser.add_argument("--url", default=resolve_default_url(), help="URL alvo. Default: index.html local em file://")
    parser.add_argument(
        "--output-json",
        default=str(PROJECT_ROOT / "qa-functional-report.json"),
        help="Arquivo de saída JSON.",
    )
    parser.add_argument(
        "--output-md",
        default=str(PROJECT_ROOT / "qa-functional-report.md"),
        help="Arquivo de saída Markdown.",
    )
    parser.add_argument(
        "--mobile-device",
        default="iPhone 12",
        help="Device profile do Playwright para auditoria mobile.",
    )
    parser.add_argument(
        "--headful",
        action="store_true",
        help="Executa com navegador visível (default é headless).",
    )
    args = parser.parse_args()

    checks: List[CheckResult] = []
    runtime_errors: List[str] = []
    target_url = args.url.strip()
    if not target_url:
        target_url = resolve_default_url()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not args.headful)

        desktop_ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        desktop_page = desktop_ctx.new_page()
        collect_console(desktop_page, runtime_errors, "desktop")
        desktop_page.goto(target_url, wait_until="domcontentloaded")
        run_desktop_checks(desktop_page, checks)
        desktop_ctx.close()

        if args.mobile_device not in playwright.devices:
            print(
                f"Aviso: device '{args.mobile_device}' não existe no Playwright. Usando 'iPhone 12'.",
                file=sys.stderr,
            )
            mobile_device = "iPhone 12"
        else:
            mobile_device = args.mobile_device

        mobile_ctx = browser.new_context(**playwright.devices[mobile_device])
        mobile_page = mobile_ctx.new_page()
        collect_console(mobile_page, runtime_errors, "mobile")
        mobile_page.goto(target_url, wait_until="domcontentloaded")
        run_mobile_checks(mobile_page, checks)
        mobile_ctx.close()

        browser.close()

    summary_desktop = summarize_scope(checks, "desktop")
    summary_mobile = summarize_scope(checks, "mobile")

    critical_total = summary_desktop["critical_total"] + summary_mobile["critical_total"]
    critical_failed = summary_desktop["critical_failed"] + summary_mobile["critical_failed"]
    overall_ok = critical_failed == 0 and len(runtime_errors) == 0

    report: Dict[str, object] = {
        "generated_at_utc": browser_time_iso(),
        "target_url": target_url,
        "checks": [asdict(item) for item in checks],
        "summary": {
            "desktop": summary_desktop,
            "mobile": summary_mobile,
        },
        "runtime_errors": runtime_errors,
        "overall": {
            "ok": overall_ok,
            "critical_total": critical_total,
            "critical_failed": critical_failed,
            "runtime_errors": len(runtime_errors),
        },
    }

    output_json = Path(args.output_json).expanduser().resolve()
    output_md = Path(args.output_md).expanduser().resolve()
    output_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    output_md.write_text(build_markdown(report), encoding="utf-8")

    print(f"JSON: {output_json}")
    print(f"MD: {output_md}")
    print(
        "Resumo:",
        f"overall_ok={overall_ok}",
        f"critical={critical_total - critical_failed}/{critical_total}",
        f"runtime_errors={len(runtime_errors)}",
    )

    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
