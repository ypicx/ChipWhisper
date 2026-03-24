#include "ct117e_lcd_parallel.h"

#define CT117E_LCD_REG_CURSOR_X 0x20U
#define CT117E_LCD_REG_CURSOR_Y 0x21U
#define CT117E_LCD_REG_GRAM 0x22U

typedef struct
{
    char ch;
    uint8_t cols[5];
} CT117ELcdGlyph5x7;

static const CT117ELcdGlyph5x7 kCt117ELcdFont5x7[] = {
    {' ', {0x00, 0x00, 0x00, 0x00, 0x00}},
    {'-', {0x08, 0x08, 0x08, 0x08, 0x08}},
    {'.', {0x00, 0x60, 0x60, 0x00, 0x00}},
    {'/', {0x20, 0x10, 0x08, 0x04, 0x02}},
    {':', {0x00, 0x36, 0x36, 0x00, 0x00}},
    {'?', {0x02, 0x01, 0x51, 0x09, 0x06}},
    {'0', {0x3E, 0x51, 0x49, 0x45, 0x3E}},
    {'1', {0x00, 0x42, 0x7F, 0x40, 0x00}},
    {'2', {0x42, 0x61, 0x51, 0x49, 0x46}},
    {'3', {0x21, 0x41, 0x45, 0x4B, 0x31}},
    {'4', {0x18, 0x14, 0x12, 0x7F, 0x10}},
    {'5', {0x27, 0x45, 0x45, 0x45, 0x39}},
    {'6', {0x3C, 0x4A, 0x49, 0x49, 0x30}},
    {'7', {0x01, 0x71, 0x09, 0x05, 0x03}},
    {'8', {0x36, 0x49, 0x49, 0x49, 0x36}},
    {'9', {0x06, 0x49, 0x49, 0x29, 0x1E}},
    {'A', {0x7E, 0x11, 0x11, 0x11, 0x7E}},
    {'B', {0x7F, 0x49, 0x49, 0x49, 0x36}},
    {'C', {0x3E, 0x41, 0x41, 0x41, 0x22}},
    {'D', {0x7F, 0x41, 0x41, 0x22, 0x1C}},
    {'E', {0x7F, 0x49, 0x49, 0x49, 0x41}},
    {'F', {0x7F, 0x09, 0x09, 0x09, 0x01}},
    {'G', {0x3E, 0x41, 0x49, 0x49, 0x7A}},
    {'H', {0x7F, 0x08, 0x08, 0x08, 0x7F}},
    {'I', {0x00, 0x41, 0x7F, 0x41, 0x00}},
    {'J', {0x20, 0x40, 0x41, 0x3F, 0x01}},
    {'K', {0x7F, 0x08, 0x14, 0x22, 0x41}},
    {'L', {0x7F, 0x40, 0x40, 0x40, 0x40}},
    {'M', {0x7F, 0x02, 0x0C, 0x02, 0x7F}},
    {'N', {0x7F, 0x04, 0x08, 0x10, 0x7F}},
    {'O', {0x3E, 0x41, 0x41, 0x41, 0x3E}},
    {'P', {0x7F, 0x09, 0x09, 0x09, 0x06}},
    {'Q', {0x3E, 0x41, 0x51, 0x21, 0x5E}},
    {'R', {0x7F, 0x09, 0x19, 0x29, 0x46}},
    {'S', {0x46, 0x49, 0x49, 0x49, 0x31}},
    {'T', {0x01, 0x01, 0x7F, 0x01, 0x01}},
    {'U', {0x3F, 0x40, 0x40, 0x40, 0x3F}},
    {'V', {0x1F, 0x20, 0x40, 0x20, 0x1F}},
    {'W', {0x3F, 0x40, 0x38, 0x40, 0x3F}},
    {'X', {0x63, 0x14, 0x08, 0x14, 0x63}},
    {'Y', {0x07, 0x08, 0x70, 0x08, 0x07}},
    {'Z', {0x61, 0x51, 0x49, 0x45, 0x43}},
};

static void CT117ELcd_GetGlyph5x7(char ch, uint8_t out[5])
{
    uint32_t index;
    uint32_t glyph_count = (uint32_t)(sizeof(kCt117ELcdFont5x7) / sizeof(kCt117ELcdFont5x7[0]));

    if (ch >= 'a' && ch <= 'z') {
        ch = (char)(ch - 'a' + 'A');
    }

    for (index = 0U; index < glyph_count; ++index) {
        if (kCt117ELcdFont5x7[index].ch == ch) {
            out[0] = kCt117ELcdFont5x7[index].cols[0];
            out[1] = kCt117ELcdFont5x7[index].cols[1];
            out[2] = kCt117ELcdFont5x7[index].cols[2];
            out[3] = kCt117ELcdFont5x7[index].cols[3];
            out[4] = kCt117ELcdFont5x7[index].cols[4];
            return;
        }
    }

    CT117ELcd_GetGlyph5x7('?', out);
}

static void CT117ELcd_SetIdleLevels(const CT117ELcdBus *bus)
{
    HAL_GPIO_WritePin(bus->cs_port, bus->cs_pin, GPIO_PIN_SET);
    HAL_GPIO_WritePin(bus->rs_port, bus->rs_pin, GPIO_PIN_SET);
    HAL_GPIO_WritePin(bus->wr_port, bus->wr_pin, GPIO_PIN_SET);
    HAL_GPIO_WritePin(bus->rd_port, bus->rd_pin, GPIO_PIN_SET);
}

static void CT117ELcd_SetBusOutput(const CT117ELcdBus *bus)
{
    GPIO_InitTypeDef gpio_init = {0};
    uint8_t index;

    gpio_init.Mode = GPIO_MODE_OUTPUT_PP;
    gpio_init.Pull = GPIO_NOPULL;
    gpio_init.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
    for (index = 0U; index < 16U; ++index) {
        gpio_init.Pin = bus->data_pins[index];
        HAL_GPIO_Init(bus->data_ports[index], &gpio_init);
    }
}

static void CT117ELcd_SetBusInput(const CT117ELcdBus *bus)
{
    GPIO_InitTypeDef gpio_init = {0};
    uint8_t index;

    gpio_init.Mode = GPIO_MODE_INPUT;
    gpio_init.Pull = GPIO_NOPULL;
    gpio_init.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
    for (index = 0U; index < 16U; ++index) {
        gpio_init.Pin = bus->data_pins[index];
        HAL_GPIO_Init(bus->data_ports[index], &gpio_init);
    }
}

static void CT117ELcd_WriteBusWord(const CT117ELcdBus *bus, uint16_t value)
{
    uint8_t index;

    for (index = 0U; index < 16U; ++index) {
        HAL_GPIO_WritePin(
            bus->data_ports[index],
            bus->data_pins[index],
            (value & (uint16_t)(1U << index)) != 0U ? GPIO_PIN_SET : GPIO_PIN_RESET
        );
    }
}

static uint16_t CT117ELcd_ReadBusWord(const CT117ELcdBus *bus)
{
    uint8_t index;
    uint16_t value = 0U;

    for (index = 0U; index < 16U; ++index) {
        if (HAL_GPIO_ReadPin(bus->data_ports[index], bus->data_pins[index]) == GPIO_PIN_SET) {
            value = (uint16_t)(value | (uint16_t)(1U << index));
        }
    }
    return value;
}

static void CT117ELcd_PulseWrite(const CT117ELcdBus *bus)
{
    HAL_GPIO_WritePin(bus->wr_port, bus->wr_pin, GPIO_PIN_RESET);
    __NOP();
    __NOP();
    __NOP();
    HAL_GPIO_WritePin(bus->wr_port, bus->wr_pin, GPIO_PIN_SET);
}

static void CT117ELcd_SelectCommand(const CT117ELcdBus *bus)
{
    HAL_GPIO_WritePin(bus->cs_port, bus->cs_pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(bus->rs_port, bus->rs_pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(bus->wr_port, bus->wr_pin, GPIO_PIN_SET);
}

static void CT117ELcd_SelectData(const CT117ELcdBus *bus)
{
    HAL_GPIO_WritePin(bus->cs_port, bus->cs_pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(bus->rs_port, bus->rs_pin, GPIO_PIN_SET);
    HAL_GPIO_WritePin(bus->wr_port, bus->wr_pin, GPIO_PIN_SET);
}

static void CT117ELcd_EndTransfer(const CT117ELcdBus *bus)
{
    HAL_GPIO_WritePin(bus->cs_port, bus->cs_pin, GPIO_PIN_SET);
    HAL_GPIO_WritePin(bus->rs_port, bus->rs_pin, GPIO_PIN_SET);
    HAL_GPIO_WritePin(bus->rd_port, bus->rd_pin, GPIO_PIN_SET);
    HAL_GPIO_WritePin(bus->wr_port, bus->wr_pin, GPIO_PIN_SET);
}

static void CT117ELcd_WriteReg(const CT117ELcdBus *bus, uint16_t reg, uint16_t value)
{
    CT117ELcd_SetBusOutput(bus);
    CT117ELcd_SelectCommand(bus);
    CT117ELcd_WriteBusWord(bus, reg);
    CT117ELcd_PulseWrite(bus);
    CT117ELcd_SelectData(bus);
    CT117ELcd_WriteBusWord(bus, value);
    CT117ELcd_PulseWrite(bus);
    CT117ELcd_EndTransfer(bus);
}

static uint16_t CT117ELcd_ReadReg(const CT117ELcdBus *bus, uint16_t reg)
{
    uint16_t value;

    CT117ELcd_SetBusOutput(bus);
    CT117ELcd_SelectCommand(bus);
    CT117ELcd_WriteBusWord(bus, reg);
    CT117ELcd_PulseWrite(bus);
    HAL_GPIO_WritePin(bus->rs_port, bus->rs_pin, GPIO_PIN_SET);
    CT117ELcd_SetBusInput(bus);
    HAL_GPIO_WritePin(bus->rd_port, bus->rd_pin, GPIO_PIN_RESET);
    __NOP();
    __NOP();
    __NOP();
    value = CT117ELcd_ReadBusWord(bus);
    HAL_GPIO_WritePin(bus->rd_port, bus->rd_pin, GPIO_PIN_SET);
    CT117ELcd_SetBusOutput(bus);
    CT117ELcd_EndTransfer(bus);
    return value;
}

static void CT117ELcd_SetCursor(const CT117ELcdBus *bus, uint16_t x, uint16_t y)
{
    CT117ELcd_WriteReg(bus, CT117E_LCD_REG_CURSOR_X, x);
    CT117ELcd_WriteReg(bus, CT117E_LCD_REG_CURSOR_Y, y);
}

static void CT117ELcd_BeginGramWrite(const CT117ELcdBus *bus)
{
    CT117ELcd_SetBusOutput(bus);
    CT117ELcd_SelectCommand(bus);
    CT117ELcd_WriteBusWord(bus, CT117E_LCD_REG_GRAM);
    CT117ELcd_PulseWrite(bus);
    CT117ELcd_SelectData(bus);
}

static void CT117ELcd_WriteRamWord(const CT117ELcdBus *bus, uint16_t value)
{
    CT117ELcd_WriteBusWord(bus, value);
    CT117ELcd_PulseWrite(bus);
}

static void CT117ELcd_Init8230(const CT117ELcdBus *bus)
{
    CT117ELcd_WriteReg(bus, 0x0000U, 0x0001U);
    HAL_Delay(100);
    CT117ELcd_WriteReg(bus, 0x0001U, 0x0000U);
    CT117ELcd_WriteReg(bus, 0x0010U, 0x1790U);
    CT117ELcd_WriteReg(bus, 0x0060U, 0x2700U);
    CT117ELcd_WriteReg(bus, 0x0061U, 0x0001U);
    CT117ELcd_WriteReg(bus, 0x0046U, 0x0002U);
    CT117ELcd_WriteReg(bus, 0x0013U, 0x8010U);
    CT117ELcd_WriteReg(bus, 0x0012U, 0x80FEU);
    CT117ELcd_WriteReg(bus, 0x0002U, 0x0500U);
    CT117ELcd_WriteReg(bus, 0x0003U, 0x1030U);
    CT117ELcd_WriteReg(bus, 0x0030U, 0x0303U);
    CT117ELcd_WriteReg(bus, 0x0031U, 0x0303U);
    CT117ELcd_WriteReg(bus, 0x0032U, 0x0303U);
    CT117ELcd_WriteReg(bus, 0x0033U, 0x0300U);
    CT117ELcd_WriteReg(bus, 0x0034U, 0x0003U);
    CT117ELcd_WriteReg(bus, 0x0035U, 0x0303U);
    CT117ELcd_WriteReg(bus, 0x0036U, 0x0014U);
    CT117ELcd_WriteReg(bus, 0x0037U, 0x0303U);
    CT117ELcd_WriteReg(bus, 0x0038U, 0x0303U);
    CT117ELcd_WriteReg(bus, 0x0039U, 0x0303U);
    CT117ELcd_WriteReg(bus, 0x003AU, 0x0300U);
    CT117ELcd_WriteReg(bus, 0x003BU, 0x0003U);
    CT117ELcd_WriteReg(bus, 0x003CU, 0x0303U);
    CT117ELcd_WriteReg(bus, 0x003DU, 0x1400U);
    CT117ELcd_WriteReg(bus, 0x0092U, 0x0200U);
    CT117ELcd_WriteReg(bus, 0x0093U, 0x0303U);
    CT117ELcd_WriteReg(bus, 0x0090U, 0x080DU);
    CT117ELcd_WriteReg(bus, 0x0003U, 0x1018U);
    CT117ELcd_WriteReg(bus, 0x0007U, 0x0173U);
}

static void CT117ELcd_Init932X(const CT117ELcdBus *bus)
{
    CT117ELcd_WriteReg(bus, 0x00E3U, 0x3008U);
    CT117ELcd_WriteReg(bus, 0x00E7U, 0x0012U);
    CT117ELcd_WriteReg(bus, 0x00EFU, 0x1231U);
    CT117ELcd_WriteReg(bus, 0x0001U, 0x0000U);
    CT117ELcd_WriteReg(bus, 0x0002U, 0x0700U);
    CT117ELcd_WriteReg(bus, 0x0003U, 0x1030U);
    CT117ELcd_WriteReg(bus, 0x0004U, 0x0000U);
    CT117ELcd_WriteReg(bus, 0x0008U, 0x0207U);
    CT117ELcd_WriteReg(bus, 0x0009U, 0x0000U);
    CT117ELcd_WriteReg(bus, 0x000AU, 0x0000U);
    CT117ELcd_WriteReg(bus, 0x000CU, 0x0000U);
    CT117ELcd_WriteReg(bus, 0x000DU, 0x0000U);
    CT117ELcd_WriteReg(bus, 0x000FU, 0x0000U);
    CT117ELcd_WriteReg(bus, 0x0010U, 0x0000U);
    CT117ELcd_WriteReg(bus, 0x0011U, 0x0007U);
    CT117ELcd_WriteReg(bus, 0x0012U, 0x0000U);
    CT117ELcd_WriteReg(bus, 0x0013U, 0x0000U);
    HAL_Delay(200);
    CT117ELcd_WriteReg(bus, 0x0010U, 0x1690U);
    CT117ELcd_WriteReg(bus, 0x0011U, 0x0227U);
    HAL_Delay(50);
    CT117ELcd_WriteReg(bus, 0x0012U, 0x001DU);
    HAL_Delay(50);
    CT117ELcd_WriteReg(bus, 0x0013U, 0x0800U);
    CT117ELcd_WriteReg(bus, 0x0029U, 0x0014U);
    CT117ELcd_WriteReg(bus, 0x002BU, 0x000BU);
    HAL_Delay(50);
    CT117ELcd_WriteReg(bus, 0x0020U, 0x0000U);
    CT117ELcd_WriteReg(bus, 0x0021U, 0x0000U);
    CT117ELcd_WriteReg(bus, 0x0030U, 0x0007U);
    CT117ELcd_WriteReg(bus, 0x0031U, 0x0707U);
    CT117ELcd_WriteReg(bus, 0x0032U, 0x0006U);
    CT117ELcd_WriteReg(bus, 0x0035U, 0x0704U);
    CT117ELcd_WriteReg(bus, 0x0036U, 0x1F04U);
    CT117ELcd_WriteReg(bus, 0x0037U, 0x0004U);
    CT117ELcd_WriteReg(bus, 0x0038U, 0x0000U);
    CT117ELcd_WriteReg(bus, 0x0039U, 0x0706U);
    CT117ELcd_WriteReg(bus, 0x003CU, 0x0701U);
    CT117ELcd_WriteReg(bus, 0x003DU, 0x000FU);
    CT117ELcd_WriteReg(bus, 0x0050U, 0x0000U);
    CT117ELcd_WriteReg(bus, 0x0051U, 0x00EFU);
    CT117ELcd_WriteReg(bus, 0x0052U, 0x0000U);
    CT117ELcd_WriteReg(bus, 0x0053U, 0x013FU);
    CT117ELcd_WriteReg(bus, 0x0060U, 0x2700U);
    CT117ELcd_WriteReg(bus, 0x0061U, 0x0001U);
    CT117ELcd_WriteReg(bus, 0x006AU, 0x0000U);
    CT117ELcd_WriteReg(bus, 0x0080U, 0x0000U);
    CT117ELcd_WriteReg(bus, 0x0081U, 0x0000U);
    CT117ELcd_WriteReg(bus, 0x0082U, 0x0000U);
    CT117ELcd_WriteReg(bus, 0x0083U, 0x0000U);
    CT117ELcd_WriteReg(bus, 0x0084U, 0x0000U);
    CT117ELcd_WriteReg(bus, 0x0085U, 0x0000U);
    CT117ELcd_WriteReg(bus, 0x0090U, 0x0010U);
    CT117ELcd_WriteReg(bus, 0x0092U, 0x0000U);
    CT117ELcd_WriteReg(bus, 0x0093U, 0x0003U);
    CT117ELcd_WriteReg(bus, 0x0095U, 0x0110U);
    CT117ELcd_WriteReg(bus, 0x0097U, 0x0000U);
    CT117ELcd_WriteReg(bus, 0x0098U, 0x0000U);
    CT117ELcd_WriteReg(bus, 0x0003U, 0x1018U);
    CT117ELcd_WriteReg(bus, 0x0007U, 0x0173U);
}

HAL_StatusTypeDef CT117ELcd_Init(const CT117ELcdBus *bus)
{
    uint16_t controller_id;

    if (bus == NULL) {
        return HAL_ERROR;
    }

    CT117ELcd_SetBusOutput(bus);
    CT117ELcd_SetIdleLevels(bus);
    HAL_Delay(5);

    controller_id = CT117ELcd_ReadReg(bus, 0x0000U);
    if (controller_id == 0x8230U) {
        CT117ELcd_Init8230(bus);
    } else {
        CT117ELcd_Init932X(bus);
    }

    return HAL_OK;
}

void CT117ELcd_Clear(const CT117ELcdBus *bus, uint16_t color)
{
    uint32_t index;

    if (bus == NULL) {
        return;
    }

    CT117ELcd_SetCursor(bus, 0U, 0U);
    CT117ELcd_BeginGramWrite(bus);
    for (index = 0U; index < (uint32_t)CT117E_LCD_WIDTH * (uint32_t)CT117E_LCD_HEIGHT; ++index) {
        CT117ELcd_WriteRamWord(bus, color);
    }
    CT117ELcd_EndTransfer(bus);
}

void CT117ELcd_DrawPixel(const CT117ELcdBus *bus, uint16_t x, uint16_t y, uint16_t color)
{
    if (bus == NULL || x >= CT117E_LCD_WIDTH || y >= CT117E_LCD_HEIGHT) {
        return;
    }

    CT117ELcd_SetCursor(bus, x, y);
    CT117ELcd_BeginGramWrite(bus);
    CT117ELcd_WriteRamWord(bus, color);
    CT117ELcd_EndTransfer(bus);
}

void CT117ELcd_WriteChar5x7(
    const CT117ELcdBus *bus,
    uint16_t x,
    uint16_t y,
    char ch,
    uint16_t foreground,
    uint16_t background
)
{
    uint8_t glyph[5] = {0};
    uint8_t column;
    uint8_t row;

    if (bus == NULL || x >= CT117E_LCD_WIDTH || y >= CT117E_LCD_HEIGHT) {
        return;
    }

    CT117ELcd_GetGlyph5x7(ch, glyph);
    for (column = 0U; column < 5U; ++column) {
        for (row = 0U; row < 7U; ++row) {
            uint16_t color = ((glyph[column] & (uint8_t)(1U << row)) != 0U) ? foreground : background;
            CT117ELcd_DrawPixel(bus, (uint16_t)(x + column), (uint16_t)(y + row), color);
        }
    }
    for (row = 0U; row < 7U; ++row) {
        CT117ELcd_DrawPixel(bus, (uint16_t)(x + 5U), (uint16_t)(y + row), background);
    }
}

void CT117ELcd_WriteString5x7(
    const CT117ELcdBus *bus,
    uint16_t x,
    uint16_t y,
    const char *text,
    uint16_t foreground,
    uint16_t background
)
{
    uint16_t cursor_x = x;
    uint16_t cursor_y = y;

    if (bus == NULL || text == NULL) {
        return;
    }

    while (*text != '\0') {
        if (*text == '\n') {
            cursor_x = x;
            cursor_y = (uint16_t)(cursor_y + 8U);
            ++text;
            continue;
        }

        if ((uint16_t)(cursor_x + 5U) >= CT117E_LCD_WIDTH) {
            cursor_x = x;
            cursor_y = (uint16_t)(cursor_y + 8U);
        }
        if ((uint16_t)(cursor_y + 6U) >= CT117E_LCD_HEIGHT) {
            return;
        }

        CT117ELcd_WriteChar5x7(bus, cursor_x, cursor_y, *text, foreground, background);
        cursor_x = (uint16_t)(cursor_x + 6U);
        ++text;
    }
}

void CT117ELcd_FillColorBars(const CT117ELcdBus *bus, uint8_t phase)
{
    static const uint16_t colors[6] = {
        CT117E_LCD_COLOR_RED,
        CT117E_LCD_COLOR_GREEN,
        CT117E_LCD_COLOR_BLUE,
        CT117E_LCD_COLOR_YELLOW,
        CT117E_LCD_COLOR_CYAN,
        CT117E_LCD_COLOR_MAGENTA,
    };
    uint16_t x;
    uint16_t y;

    if (bus == NULL) {
        return;
    }

    CT117ELcd_SetCursor(bus, 0U, 0U);
    CT117ELcd_BeginGramWrite(bus);
    for (y = 0U; y < CT117E_LCD_HEIGHT; ++y) {
        for (x = 0U; x < CT117E_LCD_WIDTH; ++x) {
            uint8_t bar = (uint8_t)((x / 40U) % 6U);
            uint8_t color_index = (uint8_t)((bar + phase) % 6U);
            CT117ELcd_WriteRamWord(bus, colors[color_index]);
        }
    }
    CT117ELcd_EndTransfer(bus);
}
