#include "kernel.h"

/* Раскладка US QWERTY, набор скан-кодов 1 */
static const char normal[128] = {
    0, 27, '1','2','3','4','5','6','7','8','9','0','-','=', '\b',
    '\t','q','w','e','r','t','y','u','i','o','p','[',']','\n',
    0, 'a','s','d','f','g','h','j','k','l',';','\'','`',
    0, '\\','z','x','c','v','b','n','m',',','.','/', 0,
    '*', 0, ' ',
};
static const char shifted[128] = {
    0, 27, '!','@','#','$','%','^','&','*','(',')','_','+', '\b',
    '\t','Q','W','E','R','T','Y','U','I','O','P','{','}','\n',
    0, 'A','S','D','F','G','H','J','K','L',':','"','~',
    0, '|','Z','X','C','V','B','N','M','<','>','?', 0,
    '*', 0, ' ',
};

#define BUF 256
static volatile char ring[BUF];
static volatile uint32_t head, tail;
static int shift, caps, ctrl;

static void push(char c) {
    uint32_t next = (head + 1) % BUF;
    if (next != tail) { ring[head] = c; head = next; }
}

static void kb_irq(struct regs *r) {
    (void)r;
    uint8_t sc = inb(0x60);
    if (sc == 0x2A || sc == 0x36) { shift = 1; return; }
    if (sc == 0xAA || sc == 0xB6) { shift = 0; return; }
    if (sc == 0x1D) { ctrl = 1; return; }
    if (sc == 0x9D) { ctrl = 0; return; }
    if (sc == 0x3A) { caps = !caps; return; }
    if (sc & 0x80) return;                       /* отпускание клавиши */
    char c = shift ? shifted[sc] : normal[sc];
    if (caps && c >= 'a' && c <= 'z') c -= 32;
    else if (caps && c >= 'A' && c <= 'Z') c += 32;
    if (ctrl && (c == 'l' || c == 'L')) c = 12;  /* Ctrl+L — очистить экран */
    if (c) push(c);
}

void keyboard_init(void) {
    while (inb(0x64) & 1) inb(0x60);             /* сбросить мусор из буфера */
    irq_register(1, kb_irq);
}

char keyboard_getchar(void) {
    while (head == tail) __asm__ volatile("hlt");
    char c = ring[tail];
    tail = (tail + 1) % BUF;
    return c;
}
