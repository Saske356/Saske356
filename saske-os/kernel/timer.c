#include "kernel.h"

static volatile uint32_t ticks;
static void tick(struct regs *r) { (void)r; ticks++; }

void timer_init(void) {
    uint32_t div = 1193182 / TIMER_HZ;
    outb(0x43, 0x36);
    outb(0x40, div & 0xFF);
    outb(0x40, div >> 8);
    irq_register(0, tick);
}

uint32_t timer_ticks(void) { return ticks; }

void sleep_ms(uint32_t ms) {
    uint32_t end = ticks + (ms * TIMER_HZ + 999) / 1000;
    while (ticks < end) __asm__ volatile("hlt");
}
