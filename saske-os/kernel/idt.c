#include "kernel.h"

/* ---------------- GDT ---------------- */
struct gdt_entry { uint16_t lim_lo, base_lo; uint8_t base_mid, access, gran, base_hi; } __attribute__((packed));
struct ptr { uint16_t limit; uint32_t base; } __attribute__((packed));

static struct gdt_entry gdt[3];
static struct ptr gdtp;
extern void gdt_flush(uint32_t);

static void gdt_set(int i, uint32_t base, uint32_t lim, uint8_t access, uint8_t gran) {
    gdt[i].base_lo = base & 0xFFFF; gdt[i].base_mid = (base >> 16) & 0xFF; gdt[i].base_hi = base >> 24;
    gdt[i].lim_lo = lim & 0xFFFF;   gdt[i].gran = ((lim >> 16) & 0x0F) | (gran & 0xF0);
    gdt[i].access = access;
}

void gdt_init(void) {
    gdt_set(0, 0, 0, 0, 0);
    gdt_set(1, 0, 0xFFFFFFFF, 0x9A, 0xCF);   /* код ядра */
    gdt_set(2, 0, 0xFFFFFFFF, 0x92, 0xCF);   /* данные ядра */
    gdtp.limit = sizeof(gdt) - 1; gdtp.base = (uint32_t)&gdt;
    gdt_flush((uint32_t)&gdtp);
}

/* ---------------- IDT ---------------- */
struct idt_entry { uint16_t base_lo, sel; uint8_t zero, flags; uint16_t base_hi; } __attribute__((packed));
static struct idt_entry idt[256];
static struct ptr idtp;
static irq_handler_t irq_handlers[16];
extern void idt_load(uint32_t);

#define DECL(n) extern void isr##n(void);
DECL(0) DECL(1) DECL(2) DECL(3) DECL(4) DECL(5) DECL(6) DECL(7) DECL(8) DECL(9) DECL(10) DECL(11)
DECL(12) DECL(13) DECL(14) DECL(15) DECL(16) DECL(17) DECL(18) DECL(19) DECL(20) DECL(21) DECL(22)
DECL(23) DECL(24) DECL(25) DECL(26) DECL(27) DECL(28) DECL(29) DECL(30) DECL(31)
#define DIRQ(n) extern void irq##n(void);
DIRQ(0) DIRQ(1) DIRQ(2) DIRQ(3) DIRQ(4) DIRQ(5) DIRQ(6) DIRQ(7) DIRQ(8) DIRQ(9) DIRQ(10) DIRQ(11)
DIRQ(12) DIRQ(13) DIRQ(14) DIRQ(15)

static void (*const stubs[48])(void) = {
    isr0, isr1, isr2, isr3, isr4, isr5, isr6, isr7, isr8, isr9, isr10, isr11, isr12, isr13, isr14, isr15,
    isr16, isr17, isr18, isr19, isr20, isr21, isr22, isr23, isr24, isr25, isr26, isr27, isr28, isr29, isr30, isr31,
    irq0, irq1, irq2, irq3, irq4, irq5, irq6, irq7, irq8, irq9, irq10, irq11, irq12, irq13, irq14, irq15,
};

static void idt_set(int n, uint32_t base) {
    idt[n].base_lo = base & 0xFFFF; idt[n].base_hi = base >> 16;
    idt[n].sel = 0x08; idt[n].zero = 0; idt[n].flags = 0x8E;
}

static void pic_remap(void) {
    uint8_t m1 = inb(0x21), m2 = inb(0xA1);
    outb(0x20, 0x11); io_wait(); outb(0xA0, 0x11); io_wait();
    outb(0x21, 0x20); io_wait(); outb(0xA1, 0x28); io_wait();   /* IRQ0-15 -> 32-47 */
    outb(0x21, 0x04); io_wait(); outb(0xA1, 0x02); io_wait();
    outb(0x21, 0x01); io_wait(); outb(0xA1, 0x01); io_wait();
    outb(0x21, m1); outb(0xA1, m2);
}

void idt_init(void) {
    pic_remap();
    for (int i = 0; i < 48; i++) idt_set(i, (uint32_t)stubs[i]);
    idtp.limit = sizeof(idt) - 1; idtp.base = (uint32_t)&idt;
    idt_load((uint32_t)&idtp);
}

void irq_register(int irq, irq_handler_t h) { irq_handlers[irq] = h; }

static const char *const exc_names[32] = {
    "Division by zero", "Debug", "NMI", "Breakpoint", "Overflow", "Bound range", "Invalid opcode",
    "Device not available", "Double fault", "Coprocessor overrun", "Invalid TSS", "Segment not present",
    "Stack fault", "General protection fault", "Page fault", "Reserved", "x87 FPU error", "Alignment check",
    "Machine check", "SIMD error", "Virtualization", "Reserved", "Reserved", "Reserved", "Reserved",
    "Reserved", "Reserved", "Reserved", "Reserved", "Reserved", "Security", "Reserved",
};

void interrupt_handler(struct regs *r) {
    if (r->int_no < 32) {
        vga_set_color(WHITE, RED);
        kprintf("\n\n  *** KERNEL PANIC: %s (int %u, err 0x%x) at EIP=0x%08x ***\n",
                exc_names[r->int_no], r->int_no, r->err_code, r->eip);
        kprintf("  EAX=%08x EBX=%08x ECX=%08x EDX=%08x\n", r->eax, r->ebx, r->ecx, r->edx);
        kprintf("  System halted.\n");
        for (;;) __asm__ volatile("cli; hlt");
    }
    int irq = r->int_no - 32;
    if (irq_handlers[irq]) irq_handlers[irq](r);
    if (irq >= 8) outb(0xA0, 0x20);
    outb(0x20, 0x20);
}
