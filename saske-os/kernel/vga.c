#include "kernel.h"

#define W 80
#define H 25
static volatile uint16_t *const buf = (uint16_t *)0xB8000;
static int row, col;
static uint8_t color = LGRAY | (BLACK << 4);

static void move_cursor(void) {
    uint16_t pos = row * W + col;
    outb(0x3D4, 0x0F); outb(0x3D5, pos & 0xFF);
    outb(0x3D4, 0x0E); outb(0x3D5, pos >> 8);
}

void vga_set_color(uint8_t fg, uint8_t bg) { color = fg | (bg << 4); }

void vga_clear(void) {
    for (int i = 0; i < W * H; i++) buf[i] = ' ' | (color << 8);
    row = col = 0;
    move_cursor();
}

void vga_init(void) {
    outb(0x3D4, 0x0A); outb(0x3D5, 14);   /* курсор-подчёркивание */
    outb(0x3D4, 0x0B); outb(0x3D5, 15);
    vga_clear();
}

static void scroll(void) {
    for (int i = 0; i < W * (H - 1); i++) buf[i] = buf[i + W];
    for (int i = W * (H - 1); i < W * H; i++) buf[i] = ' ' | (color << 8);
    row = H - 1;
}

static void serial_putc(char c) {          /* дублируем вывод в COM1 */
    while (!(inb(0x3F8 + 5) & 0x20)) ;
    outb(0x3F8, c);
}

void vga_putc(char c) {
    serial_putc(c);
    if (c == '\n') { col = 0; row++; }
    else if (c == '\r') col = 0;
    else if (c == '\t') col = (col + 4) & ~3;
    else if (c == '\b') {
        if (col > 0) col--;
        else if (row > 0) { row--; col = W - 1; }
        buf[row * W + col] = ' ' | (color << 8);
    } else {
        buf[row * W + col] = (uint8_t)c | (color << 8);
        col++;
    }
    if (col >= W) { col = 0; row++; }
    if (row >= H) scroll();
    move_cursor();
}

void vga_puts(const char *s) { while (*s) vga_putc(*s++); }

static void put_uint(uint32_t v, int base, int width, char pad) {
    char tmp[16]; int n = 0;
    do { tmp[n++] = "0123456789abcdef"[v % base]; v /= base; } while (v);
    while (n < width) tmp[n++] = pad;
    while (n) vga_putc(tmp[--n]);
}

void kprintf(const char *fmt, ...) {
    va_list ap; va_start(ap, fmt);
    for (; *fmt; fmt++) {
        if (*fmt != '%') { vga_putc(*fmt); continue; }
        fmt++;
        char pad = ' '; int width = 0;
        if (*fmt == '0') { pad = '0'; fmt++; }
        while (*fmt >= '0' && *fmt <= '9') width = width * 10 + (*fmt++ - '0');
        switch (*fmt) {
        case 'd': { int v = va_arg(ap, int);
                    if (v < 0) { vga_putc('-'); v = -v; }
                    put_uint((uint32_t)v, 10, width, pad); break; }
        case 'u': put_uint(va_arg(ap, uint32_t), 10, width, pad); break;
        case 'x': put_uint(va_arg(ap, uint32_t), 16, width, pad); break;
        case 'c': vga_putc((char)va_arg(ap, int)); break;
        case 's': { const char *s = va_arg(ap, const char *); vga_puts(s ? s : "(null)"); break; }
        case '%': vga_putc('%'); break;
        default:  vga_putc('%'); vga_putc(*fmt); break;
        }
    }
    va_end(ap);
}
