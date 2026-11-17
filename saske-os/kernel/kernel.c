#include "kernel.h"

struct multiboot_info { uint32_t flags, mem_lower, mem_upper; };

static void serial_init(void) {
    outb(0x3F8 + 1, 0x00); outb(0x3F8 + 3, 0x80);
    outb(0x3F8 + 0, 0x03); outb(0x3F8 + 1, 0x00);   /* 38400 бод */
    outb(0x3F8 + 3, 0x03); outb(0x3F8 + 2, 0xC7); outb(0x3F8 + 4, 0x0B);
}

static void ok(const char *what) {
    vga_set_color(LGRAY, BLACK); kprintf("  [");
    vga_set_color(LGREEN, BLACK); kprintf(" OK ");
    vga_set_color(LGRAY, BLACK); kprintf("] %s\n", what);
}

void kernel_main(uint32_t magic, struct multiboot_info *mbi) {
    serial_init();
    vga_init();

    vga_set_color(LCYAN, BLACK);
    kprintf("\n   ____             _         ___  ____  \n");
    kprintf("  / ___|  __ _ ___| | _____ / _ \\/ ___| \n");
    kprintf("  \\___ \\ / _` / __| |/ / _ \\ | | \\___ \\ \n");
    kprintf("   ___) | (_| \\__ \\   <  __/ |_| |___) |\n");
    kprintf("  |____/ \\__,_|___/_|\\_\\___|\\___/|____/ \n\n");

    if (magic != 0x2BADB002) {
        vga_set_color(LRED, BLACK);
        kprintf("  Not booted by a Multiboot loader (magic 0x%x)\n", magic);
        return;
    }
    gdt_init();                    ok("GDT loaded");
    idt_init();                    ok("IDT loaded, PIC remapped");
    timer_init();                  ok("PIT timer at 100 Hz");
    keyboard_init();               ok("PS/2 keyboard");
    heap_init((mbi->flags & 1) ? mbi->mem_upper : 16 * 1024);
    kprintf("  [");
    vga_set_color(LGREEN, BLACK); kprintf(" OK ");
    vga_set_color(LGRAY, BLACK);  kprintf("] Heap: %u KB, RAM: %u MB\n",
                                          (uint32_t)heap_total() / 1024, mem_total_kb() / 1024);
    fs_init();                     ok("RAM filesystem");
    __asm__ volatile("sti");
    ok("Interrupts enabled");

    kprintf("\n");
    shell_run();
}
