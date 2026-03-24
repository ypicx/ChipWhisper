from __future__ import annotations

from pathlib import Path
from typing import List

from jinja2 import Environment, FileSystemLoader, StrictUndefined


_TEMPLATE_ENV = Environment(
    loader=FileSystemLoader(str(Path(__file__).resolve().parent / "templates")),
    autoescape=False,
    keep_trailing_newline=True,
    undefined=StrictUndefined,
)


def render_peripherals_h_v2(
    handle_declarations: List[str],
    function_declarations: List[str],
) -> str:
    template = _TEMPLATE_ENV.get_template("keil_peripherals/peripherals.h.jinja")
    return template.render(
        handle_declarations=handle_declarations,
        function_declarations=function_declarations,
    )


def render_peripherals_c_v2(
    handle_definitions: List[str],
    user_code_top: str,
    gpio_init_block: str,
    init_blocks: List[str],
    msp_blocks: List[str],
    user_code_bottom: str,
) -> str:
    template = _TEMPLATE_ENV.get_template("keil_peripherals/peripherals.c.jinja")
    return template.render(
        handle_definitions=handle_definitions,
        user_code_top=user_code_top,
        gpio_init_block=gpio_init_block,
        init_blocks=init_blocks,
        msp_blocks=msp_blocks,
        user_code_bottom=user_code_bottom,
    )
