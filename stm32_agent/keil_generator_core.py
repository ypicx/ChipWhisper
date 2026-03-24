from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from jinja2 import Environment, FileSystemLoader, StrictUndefined


_TEMPLATE_ENV = Environment(
    loader=FileSystemLoader(str(Path(__file__).resolve().parent / "templates")),
    autoescape=False,
    keep_trailing_newline=True,
    undefined=StrictUndefined,
)


def render_main_c_v2(
    include_lines: List[str],
    main_init_block: str,
    init_calls: List[str],
    system_clock_block: str,
    planned_modules: List[Dict[str, str]],
) -> str:
    template = _TEMPLATE_ENV.get_template("keil_core/main.c.jinja")
    return template.render(
        include_lines=include_lines,
        main_init_block=main_init_block,
        init_calls=init_calls,
        system_clock_block=system_clock_block,
        planned_modules=planned_modules,
    )


def render_main_h_v2(
    main_hal_header: str,
    extra_headers: List[str],
) -> str:
    template = _TEMPLATE_ENV.get_template("keil_core/main.h.jinja")
    return template.render(
        main_hal_header=main_hal_header,
        extra_headers=extra_headers,
    )


def render_it_h_v2(
    guard: str,
    handler_declarations: List[str],
) -> str:
    template = _TEMPLATE_ENV.get_template("keil_core/interrupts.h.jinja")
    return template.render(
        guard=guard,
        handler_declarations=handler_declarations,
    )


def render_it_c_v2(
    include_lines: List[str],
    interrupt_blocks: List[str],
) -> str:
    template = _TEMPLATE_ENV.get_template("keil_core/interrupts.c.jinja")
    return template.render(
        include_lines=include_lines,
        interrupt_blocks=interrupt_blocks,
    )


def render_hal_msp_c_v2(global_msp_init_lines: List[str]) -> str:
    template = _TEMPLATE_ENV.get_template("keil_core/hal_msp.c.jinja")
    return template.render(
        global_msp_init_lines=global_msp_init_lines,
    )
