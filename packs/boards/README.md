# Board Packs

Place external board profiles here.

Supported layout:
- `packs/boards/<board_key>.json`

These files let users add real board constraints without editing Python source:
- board -> chip mapping
- reserved / avoid pins
- preferred on-board signals such as `led.control`, `button.input`, `uart_debug.tx`, `uart_debug.rx`

Helpful command:

```powershell
python -m stm32_agent new-board-pack my_board
```

Repo examples:

- `blue_pill_f103c8.json`
- `stm32f103c8_minimum_system.json`
- `stm32f103rb_minimum_system.json`
- `nucleo_f103rb.json`
- `stm32f103rb_training_board.json`
- `ct117e_m4_g431.json`
