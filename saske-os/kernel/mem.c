#include "kernel.h"

/* Простая куча: список блоков с первым подходящим и слиянием соседей */
struct block { size_t size; int free; struct block *next; };
extern char kernel_end[];

static struct block *heap;
static size_t total;
static uint32_t mem_kb;

#define HEAP_MAX (4 * 1024 * 1024)

void heap_init(uint32_t mem_upper_kb) {
    mem_kb = mem_upper_kb + 1024;
    uintptr_t start = ((uintptr_t)kernel_end + 15) & ~15u;
    uintptr_t limit = 0x100000 + (uintptr_t)mem_upper_kb * 1024;
    total = limit - start;
    if (total > HEAP_MAX) total = HEAP_MAX;
    heap = (struct block *)start;
    heap->size = total - sizeof(struct block);
    heap->free = 1;
    heap->next = 0;
}

void *kmalloc(size_t size) {
    size = (size + 15) & ~15u;
    for (struct block *b = heap; b; b = b->next) {
        if (!b->free || b->size < size) continue;
        if (b->size >= size + sizeof(struct block) + 16) {
            struct block *n = (struct block *)((char *)(b + 1) + size);
            n->size = b->size - size - sizeof(struct block);
            n->free = 1; n->next = b->next;
            b->size = size; b->next = n;
        }
        b->free = 0;
        return b + 1;
    }
    return 0;
}

void kfree(void *p) {
    if (!p) return;
    ((struct block *)p - 1)->free = 1;
    for (struct block *b = heap; b; b = b->next)
        while (b->free && b->next && b->next->free) {
            b->size += sizeof(struct block) + b->next->size;
            b->next = b->next->next;
        }
}

size_t heap_used(void) {
    size_t u = 0;
    for (struct block *b = heap; b; b = b->next) if (!b->free) u += b->size + sizeof(struct block);
    return u;
}
size_t heap_total(void) { return total; }
uint32_t mem_total_kb(void) { return mem_kb; }
