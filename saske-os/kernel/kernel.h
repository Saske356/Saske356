#ifndef KERNEL_H
#define KERNEL_H

#include <stdint.h>
#include <stddef.h>
#include <stdarg.h>

/* --- порты ввода-вывода --- */
static inline void outb(uint16_t p, uint8_t v) { __asm__ volatile("outb %0, %1" :: "a"(v), "Nd"(p)); }
static inline uint8_t inb(uint16_t p) { uint8_t v; __asm__ volatile("inb %1, %0" : "=a"(v) : "Nd"(p)); return v; }
static inline void io_wait(void) { outb(0x80, 0); }

/* --- строки (lib.c) --- */
size_t strlen(const char *s);
int    strcmp(const char *a, const char *b);
int    strncmp(const char *a, const char *b, size_t n);
char  *strncpy(char *d, const char *s, size_t n);
void  *memset(void *d, int c, size_t n);
void  *memcpy(void *d, const void *s, size_t n);
void  *memmove(void *d, const void *s, size_t n);
int    atoi(const char *s);

/* --- консоль (vga.c) --- */
enum { BLACK, BLUE, GREEN, CYAN, RED, MAGENTA, BROWN, LGRAY,
       DGRAY, LBLUE, LGREEN, LCYAN, LRED, LMAGENTA, YELLOW, WHITE };
void vga_init(void);
void vga_clear(void);
void vga_putc(char c);
void vga_puts(const char *s);
void vga_set_color(uint8_t fg, uint8_t bg);
void kprintf(const char *fmt, ...);

/* --- прерывания (idt.c) --- */
struct regs {
    uint32_t gs, fs, es, ds;
    uint32_t edi, esi, ebp, esp, ebx, edx, ecx, eax;
    uint32_t int_no, err_code;
    uint32_t eip, cs, eflags, useresp, ss;
};
typedef void (*irq_handler_t)(struct regs *r);
void gdt_init(void);
void idt_init(void);
void irq_register(int irq, irq_handler_t h);

/* --- таймер (timer.c) --- */
#define TIMER_HZ 100
void     timer_init(void);
uint32_t timer_ticks(void);
void     sleep_ms(uint32_t ms);

/* --- клавиатура (keyboard.c) --- */
void keyboard_init(void);
char keyboard_getchar(void);   /* блокирующее чтение */

/* --- память (mem.c) --- */
void   heap_init(uint32_t mem_upper_kb);
void  *kmalloc(size_t size);
void   kfree(void *p);
size_t heap_used(void);
size_t heap_total(void);
uint32_t mem_total_kb(void);

/* --- файловая система в памяти (fs.c) --- */
void fs_init(void);
int  fs_write(const char *name, const char *data, int append);
const char *fs_read(const char *name);
int  fs_remove(const char *name);
void fs_list(void);

/* --- оболочка (shell.c) --- */
void shell_run(void);

#endif
