from __future__ import annotations

import json
import sys
from pathlib import Path

from .app_logic_drafter import (
    draft_app_logic_for_plan,
    has_nonempty_app_logic,
    has_nonempty_generated_files,
    merge_generated_app_logic,
)
from .builder import build_project, doctor_project, list_project_builders
from .gcc_builder import build_gcc_project, doctor_gcc_project
from .cube_repository import (
    doctor_cube_f1_package,
    doctor_cube_g4_package,
    import_cube_f1_drivers,
    import_cube_g4_drivers,
)
from .cubemx_chip_import import import_cubemx_chip
from .extension_packs import (
    doctor_packs,
    export_builtin_catalog,
    init_packs_dir,
    import_module_files,
    scaffold_board_pack,
    scaffold_chip_pack,
    scaffold_module_pack,
)
from .keil_builder import build_keil_project, doctor_keil_project
from .keil_generator import scaffold_from_request
from .llm_config import LlmConfig, LlmProfile, load_llm_config
from .path_config import doctor_path_config, write_path_config_template
from .planner import plan_request, plan_request_file
from .renode_runner import doctor_renode_project, run_renode_project


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        _print_usage()
        return 2

    generate_makefile = "--makefile" in argv
    argv = [arg for arg in argv if arg != "--makefile"]

    command = argv[0]

    if command == "generate" and len(argv) in {3, 4}:
        return _run_generate_pipeline(argv, generate_makefile=generate_makefile)

    if command == "plan" and len(argv) in {2, 3}:
        request_path = Path(argv[1])
        if not request_path.exists():
            print(json.dumps({"error": f"File does not exist: {request_path}"}, ensure_ascii=False, indent=2))
            return 2

        result = plan_request_file(request_path, argv[2] if len(argv) == 3 else None)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0 if result.feasible else 1

    if command == "scaffold" and len(argv) in {3, 4}:
        request_path = Path(argv[1])
        if not request_path.exists():
            print(json.dumps({"error": f"File does not exist: {request_path}"}, ensure_ascii=False, indent=2))
            return 2
        payload = json.loads(request_path.read_text(encoding="utf-8"))
        packs_dir = argv[3] if len(argv) == 4 else None
        payload, prep_warnings = _prepare_payload_for_cli_scaffold(
            payload,
            request_path=request_path,
            packs_dir=packs_dir,
        )
        result = scaffold_from_request(payload, argv[2], packs_dir=packs_dir, generate_makefile=generate_makefile)
        result.warnings = [*result.warnings, *prep_warnings]
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0 if result.feasible else 1

    if command == "doctor-packs" and len(argv) in {1, 2}:
        result = doctor_packs(argv[1] if len(argv) == 2 else None)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0 if not result.errors else 1

    if command == "init-packs" and len(argv) in {1, 2}:
        path = init_packs_dir(argv[1] if len(argv) == 2 else None)
        print(json.dumps({"packs_dir": str(path)}, ensure_ascii=False, indent=2))
        return 0

    if command == "new-module-pack" and len(argv) in {2, 3}:
        path = scaffold_module_pack(argv[1], argv[2] if len(argv) == 3 else None)
        print(json.dumps({"module_pack_dir": str(path)}, ensure_ascii=False, indent=2))
        return 0

    if command == "new-chip-pack" and len(argv) in {2, 3}:
        path = scaffold_chip_pack(argv[1], argv[2] if len(argv) == 3 else None)
        print(json.dumps({"chip_pack_file": str(path)}, ensure_ascii=False, indent=2))
        return 0

    if command == "new-board-pack" and len(argv) in {2, 3}:
        path = scaffold_board_pack(argv[1], argv[2] if len(argv) == 3 else None)
        print(json.dumps({"board_pack_file": str(path)}, ensure_ascii=False, indent=2))
        return 0

    if command == "import-module-files" and len(argv) >= 3:
        result = import_module_files(argv[1], argv[2:])
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0

    if command == "export-builtins" and len(argv) in {1, 2}:
        path = export_builtin_catalog(argv[1] if len(argv) == 2 else None)
        print(json.dumps({"packs_dir": str(path)}, ensure_ascii=False, indent=2))
        return 0

    if command == "import-cubemx-chip" and len(argv) in {2, 3, 4}:
        reference = argv[1]
        chip_name = argv[2] if len(argv) >= 3 else None
        packs_dir = argv[3] if len(argv) == 4 else None
        result = import_cubemx_chip(reference, chip_name=chip_name, packs_dir=packs_dir)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0

    if command == "list-builders" and len(argv) == 1:
        result = [
            {
                "kind": descriptor.kind,
                "display_name": descriptor.display_name,
                "supported_project_files": list(descriptor.supported_project_files),
            }
            for descriptor in list_project_builders()
        ]
        print(json.dumps({"builders": result}, ensure_ascii=False, indent=2))
        return 0

    if command == "doctor-project" and len(argv) in {2, 3}:
        result = doctor_project(argv[1], builder_kind=argv[2] if len(argv) == 3 else "auto")
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0 if result.ready else 1

    if command == "build-project" and len(argv) >= 2:
        remaining = argv[1:]
        builder_kind = "auto"
        if "--gcc" in remaining:
            builder_kind = "gcc"
            remaining = [a for a in remaining if a != "--gcc"]
        elif "--keil" in remaining:
            builder_kind = "keil"
            remaining = [a for a in remaining if a != "--keil"]
        elif len(remaining) >= 2:
            builder_kind = remaining[1]
        result = build_project(remaining[0], builder_kind=builder_kind)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0 if result.built else 1

    if command == "doctor-keil" and len(argv) in {2, 3}:
        result = doctor_keil_project(argv[1], argv[2] if len(argv) == 3 else None)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0 if result.ready else 1

    if command == "build-keil" and len(argv) in {2, 3}:
        result = build_keil_project(argv[1], argv[2] if len(argv) == 3 else None)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0 if result.built else 1

    if command == "doctor-gcc" and len(argv) in {2, 3}:
        result = doctor_gcc_project(argv[1], argv[2] if len(argv) == 3 else None)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0 if result.ready else 1

    if command == "build-gcc" and len(argv) in {2, 3}:
        result = build_gcc_project(argv[1], argv[2] if len(argv) == 3 else None)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0 if result.built else 1

    if command == "doctor-renode" and len(argv) in {2, 3}:
        result = doctor_renode_project(argv[1], argv[2] if len(argv) == 3 else None)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0 if result.ready else 1

    if command == "simulate-renode" and len(argv) in {2, 3, 4}:
        run_seconds, renode_path = _parse_simulate_renode_args(argv[2:])
        result = run_renode_project(argv[1], renode_path=renode_path, run_seconds=run_seconds)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0 if result.ran else 1

    if command == "doctor-cubef1" and len(argv) in {1, 2, 3}:
        repository_path = argv[1] if len(argv) >= 2 else None
        package_path = argv[2] if len(argv) == 3 else None
        result = doctor_cube_f1_package(repository_path, package_path)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0 if result.ready else 1

    if command == "import-cubef1-drivers" and len(argv) in {2, 3, 4}:
        project_path = argv[1]
        repository_path = argv[2] if len(argv) >= 3 else None
        package_path = argv[3] if len(argv) == 4 else None
        result = import_cube_f1_drivers(project_path, repository_path, package_path)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0 if result.imported else 1

    if command == "doctor-cubeg4" and len(argv) in {1, 2, 3}:
        repository_path = argv[1] if len(argv) >= 2 else None
        package_path = argv[2] if len(argv) == 3 else None
        result = doctor_cube_g4_package(repository_path, package_path)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0 if result.ready else 1

    if command == "import-cubeg4-drivers" and len(argv) in {2, 3, 4}:
        project_path = argv[1]
        repository_path = argv[2] if len(argv) >= 3 else None
        package_path = argv[3] if len(argv) == 4 else None
        result = import_cube_g4_drivers(project_path, repository_path, package_path)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0 if result.imported else 1

    if command == "doctor-paths" and len(argv) in {1, 2}:
        result = doctor_path_config(argv[1] if len(argv) == 2 else None)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0

    if command == "init-paths" and len(argv) in {1, 2}:
        path = write_path_config_template(argv[1] if len(argv) == 2 else None)
        print(json.dumps({"config_path": str(path)}, ensure_ascii=False, indent=2))
        return 0

    _print_usage()
    return 2


def _print_usage() -> None:
    print("   or: python -m stm32_agent generate <request.json> <output_dir> [packs_dir]")
    print("   or: python -m stm32_agent plan <request.json> [packs_dir]")
    print("   or: python -m stm32_agent scaffold <request.json> <output_dir> [packs_dir]")
    print("   or: python -m stm32_agent doctor-packs [packs_dir]")
    print("   or: python -m stm32_agent init-packs [packs_dir]")
    print("   or: python -m stm32_agent new-module-pack <module_key> [packs_dir]")
    print("   or: python -m stm32_agent new-chip-pack <chip_name> [packs_dir]")
    print("   or: python -m stm32_agent new-board-pack <board_key> [packs_dir]")
    print("   or: python -m stm32_agent import-module-files <module_key> <file1> [file2 ...]")
    print("   or: python -m stm32_agent export-builtins [packs_dir]")
    print("   or: python -m stm32_agent import-cubemx-chip <refname|xml_path> [chip_name] [packs_dir]")
    print("   or: python -m stm32_agent list-builders")
    print("   or: python -m stm32_agent doctor-project <project_dir|project_file> [builder_kind]")
    print("   or: python -m stm32_agent build-project <project_dir|project_file> [--gcc|--keil|builder_kind]")
    print("   or: python -m stm32_agent doctor-gcc <project_dir> [arm-none-eabi-gcc]")
    print("   or: python -m stm32_agent build-gcc <project_dir> [arm-none-eabi-gcc]")
    print("   or: python -m stm32_agent doctor-keil <project_dir|project.uvprojx> [uv4.exe]")
    print("   or: python -m stm32_agent build-keil <project_dir|project.uvprojx> [uv4.exe]")
    print("   or: python -m stm32_agent doctor-renode <project_dir|project.uvprojx> [renode.exe]")
    print("   or: python -m stm32_agent simulate-renode <project_dir|project.uvprojx> [seconds] [renode.exe]")
    print("   or: python -m stm32_agent doctor-cubef1 [repository_dir] [package_dir]")
    print("   or: python -m stm32_agent import-cubef1-drivers <project_dir|project.uvprojx> [repository_dir] [package_dir]")
    print("   or: python -m stm32_agent doctor-cubeg4 [repository_dir] [package_dir]")
    print("   or: python -m stm32_agent import-cubeg4-drivers <project_dir|project.uvprojx> [repository_dir] [package_dir]")
    print("   or: python -m stm32_agent doctor-paths [config.json]")
    print("   or: python -m stm32_agent init-paths [config.json]")


def _prepare_payload_for_cli_scaffold(
    payload: dict[str, object],
    request_path: Path,
    packs_dir: str | Path | None = None,
) -> tuple[dict[str, object], list[str]]:
    working_payload = dict(payload)
    goal = str(working_payload.get("app_logic_goal", "")).strip()
    if not goal or has_nonempty_app_logic(working_payload.get("app_logic")) or has_nonempty_generated_files(
        working_payload.get("generated_files")
    ):
        return working_payload, []

    warnings: list[str] = []
    config = load_llm_config()
    warnings.extend(config.warnings)
    if config.errors:
        warnings.extend(
            f"Skipped automatic app-logic drafting: {message}"
            for message in config.errors
        )
        return working_payload, warnings

    profile, profile_warnings = _select_cli_llm_profile(config)
    warnings.extend(profile_warnings)
    if profile is None:
        return working_payload, warnings

    plan = plan_request(working_payload, packs_dir=packs_dir)
    if not plan.feasible:
        warnings.append("Skipped automatic app-logic drafting because the request could not be planned.")
        return working_payload, warnings

    draft = draft_app_logic_for_plan(
        profile,
        _build_cli_user_prompt(working_payload, request_path),
        working_payload,
        plan,
    )
    warnings.extend(draft.warnings)
    if draft.ok and (any(draft.app_logic.values()) or draft.generated_files or draft.app_logic_ir):
        return (
            merge_generated_app_logic(
                working_payload,
                draft.app_logic,
                generated_files=draft.generated_files,
                app_logic_ir=draft.app_logic_ir,
            ),
            warnings,
        )
    warnings.extend(
        f"Skipped automatic app-logic drafting: {message}"
        for message in draft.errors
    )
    return working_payload, warnings


def _select_cli_llm_profile(config: LlmConfig) -> tuple[LlmProfile | None, list[str]]:
    warnings: list[str] = []
    enabled_profiles = [profile for profile in config.profiles if profile.enabled]
    if not enabled_profiles:
        warnings.append("Skipped automatic app-logic drafting because no enabled LLM profile is configured.")
        return None, warnings

    default_profile_id = config.default_profile_id.strip()
    if default_profile_id:
        for profile in enabled_profiles:
            if profile.profile_id == default_profile_id:
                return profile, warnings
        warnings.append("Default LLM profile is unavailable or disabled; using the first enabled profile instead.")

    return enabled_profiles[0], warnings


def _build_cli_user_prompt(payload: dict[str, object], request_path: Path) -> str:
    summary = str(payload.get("summary", "")).strip()
    if summary:
        return summary
    requirements = payload.get("requirements", [])
    if isinstance(requirements, list):
        lines = [str(item).strip() for item in requirements if str(item).strip()]
        if lines:
            return "CLI scaffold request requirements:\n" + "\n".join(f"- {line}" for line in lines)
    return f"Generate application logic for the CLI scaffold request loaded from {request_path.name}."


def _parse_simulate_renode_args(args: list[str]) -> tuple[float, str | None]:
    if not args:
        return 1.0, None

    first = args[0].strip()
    if _looks_like_float(first):
        return float(first), args[1] if len(args) >= 2 else None

    return 1.0, first


def _looks_like_float(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def _run_generate_pipeline(argv: list[str], *, generate_makefile: bool = False) -> int:
    """One-click pipeline: plan → scaffold → import-drivers → build.

    Usage: generate <request.json> <output_dir> [packs_dir]
    """
    request_path = Path(argv[1])
    output_dir = argv[2]
    packs_dir = argv[3] if len(argv) == 4 else None

    if not request_path.exists():
        print(json.dumps({"error": f"File does not exist: {request_path}"}, ensure_ascii=False, indent=2))
        return 2

    pipeline_result: dict[str, object] = {
        "pipeline": "generate",
        "stages_completed": [],
        "warnings": [],
        "errors": [],
    }

    # Stage 1: Plan
    print("[1/4] Planning...", flush=True)
    plan_result = plan_request_file(request_path, packs_dir)
    if not plan_result.feasible:
        pipeline_result["errors"] = ["Planning failed: request is not feasible."]
        pipeline_result["plan_result"] = plan_result.to_dict()
        print(json.dumps(pipeline_result, ensure_ascii=False, indent=2))
        return 1
    pipeline_result["stages_completed"].append("plan")  # type: ignore[union-attr]
    print(f"  ✓ Plan OK: {len(plan_result.assignments)} pin assignments", flush=True)

    # Stage 2: Scaffold
    print("[2/4] Scaffolding project...", flush=True)
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    payload, prep_warnings = _prepare_payload_for_cli_scaffold(
        payload, request_path=request_path, packs_dir=packs_dir,
    )
    scaffold_result = scaffold_from_request(payload, output_dir, packs_dir=packs_dir, generate_makefile=generate_makefile)
    scaffold_result.warnings = [*scaffold_result.warnings, *prep_warnings]
    if not scaffold_result.feasible:
        pipeline_result["errors"] = ["Scaffolding failed."]
        pipeline_result["scaffold_result"] = scaffold_result.to_dict()
        print(json.dumps(pipeline_result, ensure_ascii=False, indent=2))
        return 1
    pipeline_result["stages_completed"].append("scaffold")  # type: ignore[union-attr]
    pipeline_result["warnings"] = list(scaffold_result.warnings)  # type: ignore[assignment]
    project_dir = scaffold_result.project_dir or output_dir
    print(f"  ✓ Scaffold OK: {project_dir}", flush=True)

    # Stage 3: Import drivers
    print("[3/4] Importing drivers...", flush=True)
    try:
        family = str(payload.get("chip", {}).get("family", "")).strip().upper() if isinstance(payload.get("chip"), dict) else ""
        if family.startswith("STM32F1"):
            driver_result = import_cube_f1_drivers(project_dir)
        elif family.startswith("STM32G4"):
            driver_result = import_cube_g4_drivers(project_dir)
        else:
            driver_result = import_cube_f1_drivers(project_dir)
        if driver_result.imported:
            pipeline_result["stages_completed"].append("import_drivers")  # type: ignore[union-attr]
            print("  ✓ Drivers imported", flush=True)
        else:
            pipeline_result["warnings"].append(  # type: ignore[union-attr]
                f"Driver import skipped or failed: {'; '.join(driver_result.warnings[:2])}"
            )
            print("  ⚠ Driver import skipped (may need manual import)", flush=True)
    except Exception as exc:
        pipeline_result["warnings"].append(f"Driver import failed: {exc}")  # type: ignore[union-attr]
        print(f"  ⚠ Driver import failed: {exc}", flush=True)

    # Stage 4: Build
    print("[4/4] Building project...", flush=True)
    try:
        build_result = build_project(project_dir)
        if build_result.built:
            pipeline_result["stages_completed"].append("build")  # type: ignore[union-attr]
            print("  ✓ Build succeeded!", flush=True)
        else:
            pipeline_result["warnings"].append(  # type: ignore[union-attr]
                f"Build failed: {'; '.join(str(e) for e in build_result.errors[:2])}"
            )
            print("  ⚠ Build failed (see warnings)", flush=True)
    except Exception as exc:
        pipeline_result["warnings"].append(f"Build step failed: {exc}")  # type: ignore[union-attr]
        print(f"  ⚠ Build step failed: {exc}", flush=True)

    pipeline_result["project_dir"] = str(project_dir)
    stage_count = len(pipeline_result["stages_completed"])  # type: ignore[arg-type]
    print(f"\nPipeline complete: {stage_count}/4 stages succeeded.", flush=True)
    print(json.dumps(pipeline_result, ensure_ascii=False, indent=2))
    return 0 if stage_count >= 2 else 1
