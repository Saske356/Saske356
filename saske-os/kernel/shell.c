#include "kernel.h"

#define LINE 256
#define MAX_ARGS 16

static uint8_t fg = WHITE;

static int readline(char *buf, int max) {
    int n = 0;
    for (;;) {
        char c = keyboard_getchar();
        if (c == '\n') { vga_putc('\n'); buf[n] = 0; return n; }
        if (c == '\b') { if (n) { n--; vga_putc('\b'); } continue; }
        if (c == 12) { buf[n] = 0; return -1; }          /* Ctrl+L */
        if (c >= 32 && c < 127 && n < max - 1) { buf[n++] = c; vga_putc(c); }
    }
}

static int split(char *s, char **argv) {
    int argc = 0;
    while (*s && argc < MAX_ARGS) {
        while (*s == ' ') *s++ = 0;
        if (!*s) break;
        argv[argc++] = s;
        while (*s && *s != ' ') s++;
    }
    return argc;
}

/* остаток строки после n-го аргумента (чтобы сохранить пробелы в тексте) */
static const char *rest(const char *line, int n) {
    while (*line == ' ') line++;
    for (int i = 0; i < n; i++) {
        while (*line && *line != ' ') line++;
        while (*line == ' ') line++;
    }
    return line;
}

static void prompt(void) {
    vga_set_color(LGREEN, BLACK); kprintf("saske");
    vga_set_color(LGRAY, BLACK);  kprintf("@");
    vga_set_color(LCYAN, BLACK);  kprintf("os");
    vga_set_color(LGRAY, BLACK);  kprintf(" $ ");
    vga_set_color(fg, BLACK);
}

static void cmd_help(void) {
    kprintf("  help              this list\n"
            "  clear             clear the screen (also Ctrl+L)\n"
            "  echo <text>       print text\n"
            "  about             about SaskeOS\n"
            "  uptime            time since boot\n"
            "  mem               memory usage\n"
            "  ls                list files\n"
            "  cat <file>        show a file\n"
            "  write <f> <text>  create/overwrite a file\n"
            "  append <f> <text> add a line to a file\n"
            "  rm <file>         delete a file\n"
            "  calc <a> <op> <b> integer math: + - * / %%\n"
            "  color <1-15>      change text color\n"
            "  sleep <ms>        wait\n"
            "  guess             number guessing game\n"
            "  panic             trigger a CPU exception (demo)\n"
            "  reboot | halt     restart or stop the machine\n");
}

static void cmd_uptime(void) {
    uint32_t s = timer_ticks() / TIMER_HZ;
    kprintf("  up %u:%02u:%02u (%u ticks)\n", s / 3600, (s / 60) % 60, s % 60, timer_ticks());
}

static void cmd_mem(void) {
    kprintf("  RAM total : %u KB\n", mem_total_kb());
    kprintf("  Heap      : %u / %u KB used\n", (uint32_t)heap_used() / 1024 + 1, (uint32_t)heap_total() / 1024);
}

static void cmd_calc(int argc, char **argv) {
    if (argc != 4) { kprintf("  usage: calc 6 * 7\n"); return; }
    int a = atoi(argv[1]), b = atoi(argv[3]);
    char op = argv[2][0];
    if ((op == '/' || op == '%') && b == 0) { kprintf("  error: division by zero\n"); return; }
    switch (op) {
    case '+': kprintf("  = %d\n", a + b); break;
    case '-': kprintf("  = %d\n", a - b); break;
    case '*': case 'x': kprintf("  = %d\n", a * b); break;
    case '/': kprintf("  = %d\n", a / b); break;
    case '%': kprintf("  = %d\n", a % b); break;
    default:  kprintf("  unknown operator '%c'\n", op);
    }
}

static void cmd_guess(void) {
    uint32_t seed = timer_ticks() * 1103515245u + 12345u;
    int target = (int)(seed >> 16) % 100 + 1, tries = 0;
    char buf[16];
    kprintf("  I picked a number from 1 to 100. Type 'q' to give up.\n");
    for (;;) {
        kprintf("  guess> ");
        if (readline(buf, sizeof buf) < 0) continue;
        if (buf[0] == 'q') { kprintf("  It was %d.\n", target); return; }
        int g = atoi(buf); tries++;
        if (g < target) kprintf("  higher\n");
        else if (g > target) kprintf("  lower\n");
        else { kprintf("  Correct! %d tries.\n", tries); return; }
    }
}

static void reboot(void) {
    __asm__ volatile("cli");
    while (inb(0x64) & 2) ;
    outb(0x64, 0xFE);                         /* сброс через контроллер клавиатуры */
    for (;;) __asm__ volatile("hlt");
}

static void execute(char *line) {
    char copy[LINE];
    strncpy(copy, line, LINE - 1); copy[LINE - 1] = 0;
    char *argv[MAX_ARGS];
    int argc = split(line, argv);
    if (!argc) return;
    const char *c = argv[0];

    if (!strcmp(c, "help")) cmd_help();
    else if (!strcmp(c, "clear")) vga_clear();
    else if (!strcmp(c, "echo")) kprintf("%s\n", rest(copy, 1));
    else if (!strcmp(c, "about")) kprintf("  SaskeOS 0.1 - 32-bit x86, Multiboot, written in C and NASM.\n"
                                          "  Protected mode, IDT/PIC, PIT timer, PS/2 keyboard, heap, RAM fs.\n");
    else if (!strcmp(c, "uptime")) cmd_uptime();
    else if (!strcmp(c, "mem")) cmd_mem();
    else if (!strcmp(c, "ls")) fs_list();
    else if (!strcmp(c, "cat")) {
        if (argc < 2) { kprintf("  usage: cat <file>\n"); return; }
        const char *d = fs_read(argv[1]);
        if (!d) kprintf("  cat: %s: no such file\n", argv[1]);
        else { kprintf("%s", d); if (*d && d[strlen(d) - 1] != '\n') vga_putc('\n'); }
    }
    else if (!strcmp(c, "write") || !strcmp(c, "append")) {
        if (argc < 2) { kprintf("  usage: %s <file> <text>\n", c); return; }
        char text[LINE + 2];
        const char *r = rest(copy, 2);
        size_t n = strlen(r);
        memcpy(text, r, n); text[n] = '\n'; text[n + 1] = 0;
        int e = fs_write(argv[1], text, c[0] == 'a');
        if (e == -1) kprintf("  bad file name\n");
        else if (e == -2) kprintf("  disk full (max 32 files)\n");
        else if (e == -3) kprintf("  out of memory\n");
    }
    else if (!strcmp(c, "rm")) {
        if (argc < 2 || fs_remove(argv[1])) kprintf("  rm: no such file\n");
    }
    else if (!strcmp(c, "calc")) cmd_calc(argc, argv);
    else if (!strcmp(c, "color")) {
        int v = argc > 1 ? atoi(argv[1]) : -1;
        if (v < 1 || v > 15) kprintf("  usage: color <1-15>\n"); else fg = v;
    }
    else if (!strcmp(c, "sleep")) sleep_ms(argc > 1 ? (uint32_t)atoi(argv[1]) : 1000);
    else if (!strcmp(c, "guess")) cmd_guess();
    else if (!strcmp(c, "panic")) __asm__ volatile("xor %%ecx, %%ecx; mov $1, %%eax; xor %%edx, %%edx; div %%ecx" ::: "eax", "ecx", "edx");
    else if (!strcmp(c, "reboot")) reboot();
    else if (!strcmp(c, "halt")) {
        kprintf("  It is now safe to turn off your computer.\n");
        __asm__ volatile("outw %0, %1" :: "a"((uint16_t)0x2000), "Nd"((uint16_t)0x604)); /* QEMU */
        for (;;) __asm__ volatile("cli; hlt");
    }
    else kprintf("  %s: command not found (try 'help')\n", c);
}

void shell_run(void) {
    vga_set_color(YELLOW, BLACK);
    kprintf("  Welcome to SaskeOS! Type 'help' for commands.\n\n");
    char line[LINE];
    for (;;) {
        prompt();
        int n = readline(line, LINE);
        vga_set_color(LGRAY, BLACK);
        if (n < 0) { vga_clear(); continue; }
        execute(line);
    }
}
